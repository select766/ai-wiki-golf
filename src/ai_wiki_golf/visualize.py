from __future__ import annotations

from pathlib import Path
from typing import Any

import gradio as gr
import yaml

from .evaluation import summarize_evaluation_results


def launch_dashboard(experiment_dir: str) -> None:
    exp_path = Path(experiment_dir).resolve()

    with gr.Blocks(title="AI Wikipedia Golf Dashboard") as demo:
        gr.Markdown("# Wikipedia Golf Runs\n実験ディレクトリを指定し、各プレイの詳細を確認してください。")
        exp_input = gr.Textbox(label="Experiment Directory", value=str(exp_path))
        refresh_btn = gr.Button("Load Experiment")

        with gr.Tabs():
            with gr.Tab("Runs"):
                summary_table = gr.Dataframe(
                    headers=["Log", "Start", "Goal", "Score", "Steps"],
                    datatype=["str", "str", "str", "number", "number"],
                    interactive=False,
                )
                log_selector = gr.Dropdown(label="Select Log", choices=[])
                game_md = gr.Markdown(label="Game Summary")
                chat_md = gr.Markdown(label="Chat Log")
                book_md = gr.Markdown(label="Guide")

            with gr.Tab("Evaluations"):
                eval_summary_table = gr.Dataframe(
                    headers=["Book", "Success", "Attempts", "Success Rate (%)"],
                    datatype=["number", "number", "number", "number"],
                    interactive=False,
                )
                eval_logs_table = gr.Dataframe(
                    headers=["Log", "Book", "Start", "Goal", "Score", "Success"],
                    datatype=["str", "number", "str", "str", "number", "str"],
                    interactive=False,
                )
                eval_log_selector = gr.Dropdown(label="Select Evaluation Log", choices=[])
                eval_game_md = gr.Markdown(label="Evaluation Summary")
                eval_chat_md = gr.Markdown(label="Chat Log")
                eval_book_md = gr.Markdown(label="Guide")

        def load_run_overview(path: str):
            exp = Path(path)
            logs_dir = exp / "logs"
            rows: list[list[Any]] = []
            options: list[str] = []
            if logs_dir.exists():
                for log_file in sorted(logs_dir.glob("*.yaml")):
                    data = _safe_load_yaml(log_file)
                    history = data.get("game", {}).get("history", [])
                    rows.append(
                        [
                            log_file.name,
                            data.get("game", {}).get("start", "-"),
                            data.get("game", {}).get("goal", "-"),
                            data.get("game", {}).get("score", "-"),
                            len(history),
                        ]
                    )
                    options.append(log_file.name)
            default = options[0] if options else None
            return rows, gr.update(choices=options, value=default)

        def load_eval_overview(path: str):
            exp = Path(path)
            eval_dir = exp / "evaluates"
            rows: list[list[Any]] = []
            options: list[str] = []
            if eval_dir.exists():
                for log_file in sorted(eval_dir.glob("*.yaml")):
                    data = _safe_load_yaml(log_file)
                    game = data.get("game", {})
                    score = game.get("score", "-")
                    rows.append(
                        [
                            log_file.name,
                            data.get("book_index", "-"),
                            game.get("start", "-"),
                            game.get("goal", "-"),
                            score,
                            _format_success(score),
                        ]
                    )
                    options.append(log_file.name)
            default = options[0] if options else None
            return rows, gr.update(choices=options, value=default)

        def load_eval_stats_table(path: str):
            stats = summarize_evaluation_results(path)
            return [
                [
                    entry["book_index"],
                    entry["success_count"],
                    entry["total_runs"],
                    round(entry["success_rate"] * 100, 1),
                ]
                for entry in stats
            ]

        def load_run_detail(path: str, log_name: str | None):
            return _load_detail(Path(path), log_name, subdir="logs")

        def load_eval_detail(path: str, log_name: str | None):
            return _load_detail(Path(path), log_name, subdir="evaluates")

        run_event = refresh_btn.click(load_run_overview, inputs=exp_input, outputs=[summary_table, log_selector])
        run_event.then(load_run_detail, inputs=[exp_input, log_selector], outputs=[game_md, chat_md, book_md])

        eval_event = refresh_btn.click(
            load_eval_overview, inputs=exp_input, outputs=[eval_logs_table, eval_log_selector]
        )
        eval_event.then(
            load_eval_detail,
            inputs=[exp_input, eval_log_selector],
            outputs=[eval_game_md, eval_chat_md, eval_book_md],
        )

        refresh_btn.click(load_eval_stats_table, inputs=exp_input, outputs=eval_summary_table)

        log_selector.change(load_run_detail, inputs=[exp_input, log_selector], outputs=[game_md, chat_md, book_md])
        eval_log_selector.change(
            load_eval_detail,
            inputs=[exp_input, eval_log_selector],
            outputs=[eval_game_md, eval_chat_md, eval_book_md],
        )

    demo.launch()


def _load_detail(base_path: Path, log_name: str | None, subdir: str) -> tuple[str, str, str]:
    if not log_name:
        return "(ログを選択してください)", "", ""

    log_path = base_path / subdir / log_name
    if not log_path.exists():
        return "ログが見つかりません", "", ""

    data = _safe_load_yaml(log_path)
    game = data.get("game", {})
    history_lines = [
        f"{idx + 1}. {step.get('current', '-')} -> {step.get('choice', '-')}"
        for idx, step in enumerate(game.get("history", []))
    ]
    game_summary = (
        f"**Start:** {game.get('start')}\n\n"
        f"**Goal:** {game.get('goal')}\n\n"
        f"**Score:** {game.get('score')}\n\n"
        "**History:**\n" + ("\n".join(history_lines) if history_lines else "(なし)")
    )

    messages = data.get("messages", [])
    chat_lines = [f"### {m.get('role', 'unknown')}\n{m.get('content', '')}" for m in messages]
    chat_text = "\n\n".join(chat_lines)

    if subdir == "logs":
        iteration = _infer_iteration(log_name)
        book_filename = f"{iteration}.txt"
    else:
        book_index = data.get("book_index")
        book_filename = f"{book_index}.txt" if book_index is not None else None

    guide_text = "(書籍なし)"
    if book_filename:
        book_path = base_path / "books" / book_filename
        if book_path.exists():
            guide_text = book_path.read_text(encoding="utf-8")

    return game_summary, chat_text, guide_text


def _safe_load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data or {}
    except yaml.YAMLError:
        return {}


def _format_success(score: Any) -> str:
    if isinstance(score, (int, float)):
        return "✅" if score != 9999 else "❌"
    return "-"


def _infer_iteration(log_name: str) -> str:
    if log_name.endswith(".yaml"):
        return log_name[:-5]
    return log_name
