from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .config import ExperimentConfig
from .experiment import _build_log_payload
from .game import WikipediaGolfRunner
from .llm import build_llm_client


def evaluate_books(experiment_dir: str) -> None:
    exp_path = Path(experiment_dir)
    config_path = exp_path / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError("config.yaml not found")

    load_dotenv(exp_path / ".env")
    load_dotenv()
    config = ExperimentConfig.load(config_path)
    llm_client = build_llm_client(config.llm, os.environ)
    runner = WikipediaGolfRunner(config, llm_client)

    books_dir = exp_path / "books"
    eval_dir = exp_path / "evaluates"
    eval_dir.mkdir(parents=True, exist_ok=True)

    target_indices = [i for i in range(0, 101, 100) if (books_dir / f"{i}.txt").exists()]
    if not target_indices:
        raise RuntimeError("No evaluation targets found (books/{i}.txt missing)")

    pairs = _load_eval_pairs(config, exp_path)
    for idx in target_indices:
        guide = (books_dir / f"{idx}.txt").read_text(encoding="utf-8")
        for pair_idx, pair in enumerate(pairs, start=1):
            outcome = runner.play(
                guide_text=guide,
                start=pair["start"],
                goal=pair["goal"],
                update_book=False,
            )
            payload = _build_log_payload(config, outcome)
            payload["book_index"] = idx
            payload["pair"] = pair
            log_path = eval_dir / f"book_{idx:02d}_pair_{pair_idx:02d}.yaml"
            log_path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")


def summarize_evaluation_results(experiment_dir: str) -> list[dict[str, Any]]:
    """Aggregate evaluation logs and compute per-book success rates."""

    exp_path = Path(experiment_dir)
    eval_dir = exp_path / "evaluates"
    if not eval_dir.exists():
        return []

    stats: dict[int, dict[str, float]] = defaultdict(lambda: {"success": 0, "total": 0})

    for log_file in eval_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(log_file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue

        book_index = data.get("book_index")
        if book_index is None:
            book_index = _extract_book_index(log_file.stem)
        if book_index is None:
            continue

        score = data.get("game", {}).get("score")
        success = isinstance(score, (int, float)) and score != 9999
        stats[book_index]["total"] += 1
        if success:
            stats[book_index]["success"] += 1

    results: list[dict[str, Any]] = []
    for idx in sorted(stats):
        total = stats[idx]["total"] or 0
        success = stats[idx]["success"] or 0
        success_rate = success / total if total else 0.0
        results.append(
            {
                "book_index": idx,
                "success_count": int(success),
                "total_runs": int(total),
                "success_rate": success_rate,
            }
        )

    return results


def _load_eval_pairs(config: ExperimentConfig, exp_path: Path) -> list[dict[str, Any]]:
    if config.evaluation_pairs:
        return config.evaluation_pairs
    default_path = exp_path / "evaluation_pairs.yaml"
    if default_path.exists():
        return yaml.safe_load(default_path.read_text(encoding="utf-8"))
    built_in = Path(__file__).resolve().parent.parent / "data" / "eval_pairs.yaml"
    if built_in.exists():
        return yaml.safe_load(built_in.read_text(encoding="utf-8"))
    raise RuntimeError("Evaluation pairs not provided. Set evaluation_pairs in config or add evaluation_pairs.yaml.")


def _extract_book_index(log_stem: str) -> int | None:
    if not log_stem.startswith("book_"):
        return None
    parts = log_stem.split("_")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None
