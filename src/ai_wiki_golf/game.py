from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, Iterable

from .config import ExperimentConfig
from .llm import BaseLLMClient, LLMResult
from .mediawiki import (
    get_backlink_count,
    get_links,
    get_page_abstract,
    get_random_pages,
)


@dataclass
class StepRecord:
    current: str
    candidates: list[str]
    choice: str


@dataclass
class GameOutcome:
    start: str
    goal: str
    score: int
    success: bool
    steps: list[StepRecord]
    messages: list[dict[str, str]]
    usage: dict[str, Any]
    final_book: str | None = None

# TODO: exclude_digit_links の場合、そのことをプロンプトにも記載

class WikipediaGolfRunner:
    BOOK_CHAR_LIMIT = 2000
    LINK_SAMPLE_SEED = 20251113

    def __init__(self, config: ExperimentConfig, llm: BaseLLMClient):
        self.config = config
        self.llm = llm
        self.rng = random.Random(config.loop.seed)

    def generate_initial_book(self) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
        prompt = (
            "Wikipediaゴルフの攻略本を執筆してください。\n"
            "条件:\n"
            "- ルール: スタートとゴールのWikipediaページ間をリンクのみで移動し、20手以内で到達する。\n"
            f"- 日本語の文章で{self.BOOK_CHAR_LIMIT}文字以内。\n"
            "- 箇条書き中心で、具体的なテクニックや判断基準を記してください。\n"
            "- 前向きなトーンで簡潔に。\n"
            "攻略本のみを出力し、余分な文章を含めないでください。"
        )
        messages = [{"role": "user", "content": prompt}]
        result = self.llm.generate(messages)
        usage = _merge_usage({}, result.usage)
        book = self._clean_book_text(result.text)
        if len(book) > self.BOOK_CHAR_LIMIT:
            messages.append({"role": "assistant", "content": result.text})
            book, usage = self._request_shorter_book(messages, usage, len(book))
        else:
            book = book[: self.BOOK_CHAR_LIMIT]
        return book, messages, usage

    def play(
        self,
        guide_text: str,
        *,
        start: str | None = None,
        goal: str | None = None,
        update_book: bool = True,
    ) -> GameOutcome:
        if start is None or goal is None:
            start, goal = self._choose_start_goal()
        history = [start]
        steps: list[StepRecord] = []
        messages: list[dict[str, str]] = []
        usage: dict[str, Any] = {}
        success = False
        goal_abstract: str | None = None
        if self.config.game.include_goal_abstract:
            goal_abstract = get_page_abstract(goal)

        for turn in range(1, self.config.game.max_steps + 1):
            current = history[-1]
            candidates = self._build_candidates(current, history)
            if not candidates:
                break
            prompt = self._build_turn_prompt(
                guide_text=guide_text,
                start=start,
                goal=goal,
                current=current,
                history=history,
                candidates=candidates,
                turn=turn,
                goal_abstract=goal_abstract if turn == 1 else None,
                include_intro=(turn == 1),
            )
            messages.append({"role": "user", "content": prompt})
            llm_result = self.llm.generate(messages)
            usage = _merge_usage(usage, llm_result.usage)
            assistant_text = llm_result.text
            messages.append({"role": "assistant", "content": assistant_text})

            move, valid = self._extract_move(assistant_text, candidates)
            invalid_attempts = 0
            while not valid:
                invalid_attempts += 1
                if invalid_attempts >= self.config.game.retry_limit:
                    return self._finalize_outcome(
                        start,
                        goal,
                        steps,
                        success=False,
                        messages=messages,
                        usage=usage,
                        guide_text=guide_text,
                        update_book=update_book,
                    )
                correction_prompt = (
                    f"\n「{move or '不明'}」は選択肢に存在しません。"
                    f"選択肢: {'|'.join(candidates)}。\n"
                    "ゴールに近づくため、次に移動するページを選択肢から1つだけ選んでください。1行目に『考察: 検討過程(100文字まで)』、2行目に『移動先: 選択肢』としてください。"
                )
                messages.append({"role": "user", "content": correction_prompt})
                retry_result = self.llm.generate(messages)
                usage = _merge_usage(usage, retry_result.usage)
                messages.append({"role": "assistant", "content": retry_result.text})
                move, valid = self._extract_move(retry_result.text, candidates)

            history.append(move)
            steps.append(StepRecord(current=current, candidates=candidates, choice=move))
            if move == goal:
                success = True
                break

        score = len(steps) if success else 9999
        return self._finalize_outcome(
            start,
            goal,
            steps,
            success,
            messages,
            usage,
            guide_text,
            update_book,
        )

    def _finalize_outcome(
        self,
        start: str,
        goal: str,
        steps: list[StepRecord],
        success: bool,
        messages: list[dict[str, str]],
        usage: dict[str, Any],
        guide_text: str,
        update_book: bool,
    ) -> GameOutcome:
        score = len(steps) if success else 9999
        final_book = guide_text
        if update_book:
            review_prompt = self._build_review_prompt(start, goal, steps, success)
            messages.append({"role": "user", "content": review_prompt})
            review_result = self.llm.generate(messages)
            usage = _merge_usage(usage, review_result.usage)
            messages.append({"role": "assistant", "content": review_result.text})
            draft_book = self._clean_book_text(review_result.text)
            if len(draft_book) > self.BOOK_CHAR_LIMIT:
                final_book, usage = self._request_shorter_book(
                    messages, usage, len(draft_book)
                )
            else:
                final_book = draft_book[: self.BOOK_CHAR_LIMIT]
        return GameOutcome(
            start=start,
            goal=goal,
            score=score,
            success=success,
            steps=steps,
            messages=messages,
            usage=usage,
            final_book=final_book,
        )

    def _build_turn_prompt(
        self,
        *,
        guide_text: str,
        start: str,
        goal: str,
        current: str,
        history: list[str],
        candidates: list[str],
        turn: int,
        goal_abstract: str | None = None,
        include_intro: bool = False,
    ) -> str:
        history_text = "->".join(history)
        candidate_str = "|".join(candidates)
        goal_description = f"- ゴール概要: {goal_abstract}\n" if goal_abstract else ""
        parts = []
        if include_intro:
            parts.append(
                "あなたはWikipediaゴルフのプレイヤーです。\n"
                "基本ルール:\n"
                "- スタートとゴールのWikipediaページの間をリンクだけで移動します。\n"
                "- 1ターンでできることは、現在のページからリンクされたページ、または過去に訪れたページへ戻ること。\n"
                "- 20ターン以内にゴールへ到達できない場合は失敗。\n"
                f"- 提示されるリンク数は最大{self.config.game.max_links}個。これ以上存在する場合はランダムに選ばれる。\n"
            )
            guide_section = guide_text.strip()
            parts.append("攻略本:\n" + guide_section)
            parts.append(
                "行動のルール:\n"
                "- 訪問済みページへ戻るか、現在のページのリンクから1つを選ぶ。\n"
                "- 簡潔に考察し、最後の行は『移動先: 候補名』とする。"
            )
        parts.append("状況:")
        parts.append(f"- ゴール: {goal}")
        parts.append(f"- 現在地: {current}")
        parts.append(f"- 移動履歴: {history_text}")
        parts.append(f"- ターン: {turn}/{self.config.game.max_steps}")
        parts.append(f"- 選択肢(|区切り): {candidate_str}")
        if goal_description:
            parts.append(goal_description.rstrip())
        parts.append(
            "ゴールに近づくため、次に移動するページを選択肢から1つだけ選んでください。1行目に『考察: 検討過程(100文字まで)』、2行目に『移動先: 選択肢』としてください。"
        )
        return "\n".join(parts)

    def _build_review_prompt(
        self,
        start: str,
        goal: str,
        steps: list[StepRecord],
        success: bool,
    ) -> str:
        status = "成功" if success else "失敗"
        history_lines = [
            f"- {idx+1}手目 {step.current} -> {step.choice}" for idx, step in enumerate(steps)
        ]
        history_text = "\n".join(history_lines) or "(移動なし)"
        return (
            f"今回のゲーム結果: {status}. スタート={start}, ゴール={goal}, 手数={len(steps)}。\n"
            "上記の対話履歴と移動履歴を踏まえ、攻略本をアップデートしてください。\n"
            "条件:\n"
            f"- 日本語で{self.BOOK_CHAR_LIMIT}文字以内。\n"
            "- 箇条書きまたは短い段落で、観察から得た学びを一般化したテクニックとして記述する。\n"
            "- スタートとゴールはプレイごとに変化する。「今回」「プレイ」「移動履歴」などの語や、スタート/ゴール/訪問ページの固有名詞を直接書かず、単体で読んでも成立する内容にする。\n"
            "- 「失敗」「成功」といった語を避け、常に前向きな助言としてまとめる。\n"
            "- 攻略本のみを出力し、それ以外の文章は書かない。\n"
            "移動履歴:\n"
            f"{history_text}"
        )

    def _choose_start_goal(self) -> tuple[str, str]:
        min_backlinks = max(0, self.config.game.min_goal_backlinks)
        while True:
            pages = get_random_pages(limit=2)
            if len(pages) == 2 and pages[0] != pages[1]:
                start, goal = pages[0], pages[1]
                if min_backlinks <= 0:
                    return start, goal
                goal_backlinks = get_backlink_count(goal)
                if goal_backlinks >= min_backlinks:
                    return start, goal

    def _build_candidates(self, current: str, history: list[str]) -> list[str]:
        past = list(dict.fromkeys(reversed(history[:-1])))
        links = get_links(current) or []
        filtered_links = [link for link in links if self._allowed_link(link)]
        max_links = self.config.game.max_links
        if max_links > 0 and len(filtered_links) > max_links:
            # Reinitialize a deterministic RNG each time before sampling.
            sampler = random.Random(self.LINK_SAMPLE_SEED)
            sampled_links = sampler.sample(filtered_links, max_links)
            limited_links = sorted(sampled_links)
        else:
            limited_links = filtered_links[:]
        seen = set()
        ordered: list[str] = []
        for item in past + limited_links:
            if item not in seen and item != current:
                seen.add(item)
                ordered.append(item)
        return ordered

    def _allowed_link(self, link: str) -> bool:
        if not self.config.game.exclude_digit_links:
            return True
        return not bool(re.search(r"[0-9０-９]", link))

    def _extract_move(self, text: str, candidates: Iterable[str]) -> tuple[str | None, bool]:
        matches = list(re.finditer(r"移動先\s*[:：]\s*(.+)", text))
        if not matches:
            return None, False
        move = matches[-1].group(1).strip()
        move = move.splitlines()[0].strip()
        move = re.sub(r"[。．\.\!！?？]+$", "", move).strip()
        if move.endswith("です"):
            move = move[:-2].strip()
        for cand in candidates:
            if cand == move:
                return move, True
        return move, False

    def _clean_book_text(self, text: str) -> str:
        cleaned = text.strip()
        replacements = {
            "今回": "",
            "このプレイ": "",
            "このゲーム": "",
            "プレイ": "戦略",
            "移動履歴": "過去の判断",
        }
        for phrase, repl in replacements.items():
            cleaned = cleaned.replace(phrase, repl)
        return cleaned

    def _request_shorter_book(
        self,
        messages: list[dict[str, str]],
        usage: dict[str, Any],
        current_length: int,
    ) -> tuple[str, dict[str, Any]]:
        limit = self.BOOK_CHAR_LIMIT
        messages.append(
            {
                "role": "user",
                "content": (
                    f"攻略本は{limit}文字以内です。"
                    f"先ほどの草稿は{current_length}文字あり、制限を超えています。"
                    "箇条書き中心の実践的な攻略本のみを書き直し、余分な前置きや説明は含めないでください。"
                ),
            }
        )
        retry = self.llm.generate(messages)
        usage = _merge_usage(usage, retry.usage)
        messages.append({"role": "assistant", "content": retry.text})
        cleaned_retry = self._clean_book_text(retry.text)
        if len(cleaned_retry) > limit:
            cleaned_retry = cleaned_retry[:limit]
        return cleaned_retry, usage


def _merge_usage(base: dict[str, Any], addon: dict[str, Any]) -> dict[str, Any]:
    base = base or {}
    result = dict(base)
    for key, value in addon.items():
        if value is None:
            continue
        result[key] = (result.get(key, 0) or 0) + value
    return result
