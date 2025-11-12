#!/usr/bin/env python3
"""Generate random Wikipedia evaluation pairs for AI Wikipedia Golf."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import importlib.util
import requests
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"


def _load_mediawiki_module():
    module_path = SRC_DIR / "ai_wiki_golf" / "mediawiki.py"
    spec = importlib.util.spec_from_file_location("ai_wiki_golf.mediawiki", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load mediawiki module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mediawiki = _load_mediawiki_module()
get_random_pages = mediawiki.get_random_pages


def fetch_random_titles(limit: int, retries: int = 5) -> list[str]:
    """Return `limit` random article titles using the shared mediawiki helper."""

    delay = 1.0
    for attempt in range(retries):
        try:
            titles = get_random_pages(limit)
            if not titles:
                raise RuntimeError("Wikipedia API returned no titles")
            return titles
        except requests.RequestException as exc:  # pragma: no cover - network path
            if attempt == retries - 1:
                raise RuntimeError("Failed to fetch random titles") from exc
            time.sleep(delay)
            delay *= 2

    raise RuntimeError("Failed to fetch random titles after retries")


def generate_pairs(count: int) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []
    while len(pairs) < count:
        titles = fetch_random_titles(limit=2)
        if len(titles) < 2:
            continue
        start, goal = titles
        if start == goal:
            continue
        pairs.append({"start": start, "goal": goal})

    return pairs


def write_pairs(pairs: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(pairs, fh, allow_unicode=True, sort_keys=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of evaluation pairs to generate (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/eval_pairs.yaml"),
        help="Path to the YAML file to write",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.count < 1:
        raise SystemExit("--count must be at least 1")

    pairs = generate_pairs(args.count)
    write_pairs(pairs, args.output)
    print(f"Wrote {len(pairs)} pairs to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
