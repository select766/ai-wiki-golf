from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .config import ExperimentConfig
from .game import GameOutcome, StepRecord, WikipediaGolfRunner
from .llm import build_llm_client


def run_experiment(experiment_dir: str) -> None:
    exp_path = Path(experiment_dir)
    config_path = exp_path / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"config.yaml not found in {experiment_dir}")

    load_dotenv(exp_path / ".env")
    load_dotenv()
    config = ExperimentConfig.load(config_path)

    books_dir = exp_path / "books"
    logs_dir = exp_path / "logs"
    books_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    llm_client = build_llm_client(config.llm, os.environ)
    runner = WikipediaGolfRunner(config, llm_client)

    initial_book_path = books_dir / "0.txt"
    if initial_book_path.exists():
        guide = initial_book_path.read_text(encoding="utf-8")
    else:
        initial_book, _, _ = runner.generate_initial_book()
        initial_book_path.write_text(initial_book, encoding="utf-8")
        guide = initial_book

    latest_book_idx = _latest_book_index(books_dir)
    guide_path = books_dir / f"{latest_book_idx}.txt"
    if guide_path.exists():
        guide = guide_path.read_text(encoding="utf-8")

    start_iteration = latest_book_idx + 1
    if start_iteration > config.loop.iterations:
        print(f"All {config.loop.iterations} iterations already completed for {experiment_dir}.")
        return

    for iteration in range(start_iteration, config.loop.iterations + 1):
        outcome = runner.play(guide_text=guide, update_book=True)
        guide = outcome.final_book or guide
        (books_dir / f"{iteration}.txt").write_text(guide, encoding="utf-8")
        log_path = logs_dir / f"{iteration}.yaml"
        log_payload = _build_log_payload(config, outcome)
        log_path.write_text(yaml.safe_dump(log_payload, allow_unicode=True), encoding="utf-8")


def _build_log_payload(config: ExperimentConfig, outcome: GameOutcome) -> dict[str, Any]:
    return {
        "config": config.to_dict(),
        "messages": outcome.messages,
        "game": {
            "start": outcome.start,
            "goal": outcome.goal,
            "score": outcome.score,
            "history": [
                {
                    "current": step.current,
                    "candidates": step.candidates,
                    "choice": step.choice,
                }
                for step in outcome.steps
            ],
        },
        "cost": outcome.usage,
    }


def _latest_book_index(books_dir: Path) -> int:
    indices: list[int] = []
    for path in books_dir.glob("*.txt"):
        try:
            idx = int(path.stem)
        except ValueError:
            continue
        indices.append(idx)
    return max(indices) if indices else 0
