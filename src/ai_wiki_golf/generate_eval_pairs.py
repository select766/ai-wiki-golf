"""Command-line helper to build evaluation_pairs.yaml for experiments."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Iterable, Sequence

import requests
import yaml

from .config import ExperimentConfig
from .mediawiki import MediaWikiClient


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "experiment",
        type=Path,
        help="Path to the experiment directory that contains config.yaml",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of evaluation pairs to generate (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path (defaults to <experiment>/evaluation_pairs.yaml)",
    )
    parser.add_argument(
        "--min-goal-backlinks",
        type=int,
        default=None,
        help="Override minimum backlinks for goal pages (defaults to config value)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=2000,
        help="Maximum attempts to collect pairs before failing (default: 2000)",
    )
    return parser.parse_args(argv)


def load_config(exp_dir: Path) -> ExperimentConfig:
    config_path = exp_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"config.yaml not found under {exp_dir}")
    return ExperimentConfig.load(config_path)


def build_mediawiki_client(config: ExperimentConfig) -> MediaWikiClient:
    return MediaWikiClient(config.wiki.api_url)


def generate_pairs(
    client: MediaWikiClient,
    count: int,
    *,
    min_goal_backlinks: int,
    max_attempts: int,
) -> list[dict[str, str]]:
    if count < 1:
        raise ValueError("count must be at least 1")
    attempts = 0
    delay = 1.0
    pairs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    while len(pairs) < count:
        if attempts >= max_attempts:
            raise RuntimeError(
                "Failed to collect enough evaluation pairs. Increase --max-attempts or relax constraints."
            )
        try:
            titles = client.get_random_pages(limit=2)
        except requests.RequestException:  # pragma: no cover - network path
            time.sleep(delay)
            delay = min(delay * 1.5, 10)
            continue

        if len(titles) < 2:
            continue
        attempts += 1
        start, goal = titles[0], titles[1]
        if start == goal:
            continue
        if min_goal_backlinks > 0:
            try:
                backlinks = client.get_backlink_count(goal)
            except requests.RequestException:  # pragma: no cover - network path
                time.sleep(delay)
                delay = min(delay * 1.5, 10)
                continue
            if backlinks < min_goal_backlinks:
                continue
        candidate = (start, goal)
        if candidate in seen:
            continue
        seen.add(candidate)
        pairs.append({"start": start, "goal": goal})

    return pairs


def write_pairs(pairs: Iterable[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(list(pairs), fh, allow_unicode=True, sort_keys=False)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    experiment_dir = args.experiment.resolve()
    config = load_config(experiment_dir)
    client = build_mediawiki_client(config)
    min_goal_backlinks = (
        args.min_goal_backlinks
        if args.min_goal_backlinks is not None
        else max(0, config.game.min_goal_backlinks)
    )
    output_path = (args.output or (experiment_dir / "evaluation_pairs.yaml")).resolve()

    pairs = generate_pairs(
        client,
        args.count,
        min_goal_backlinks=min_goal_backlinks,
        max_attempts=max(1, args.max_attempts),
    )
    write_pairs(pairs, output_path)
    print(
        "Wrote {count} pairs for {experiment} -> {output}".format(
            count=len(pairs), experiment=experiment_dir, output=output_path
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
