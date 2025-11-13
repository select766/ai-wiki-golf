from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


@dataclass
class LLMConfig:
    provider: Literal["openrouter", "gemini"]
    model: str
    options: dict[str, Any] = field(default_factory=dict)
    base_url: str | None = None
    timeout: float | None = 120.0


@dataclass
class GameConfig:
    max_steps: int = 20
    max_links: int = 100
    exclude_digit_links: bool = True
    retry_limit: int = 3
    include_goal_abstract: bool = False
    min_goal_backlinks: int = 1


@dataclass
class LoopConfig:
    iterations: int = 1
    seed: int | None = None


@dataclass
class ExperimentConfig:
    llm: LLMConfig
    game: GameConfig = field(default_factory=GameConfig)
    loop: LoopConfig = field(default_factory=LoopConfig)
    evaluation_pairs: list[dict[str, str]] | None = None

    @classmethod
    def load(cls, path: Path) -> "ExperimentConfig":
        config_dict = yaml.safe_load(path.read_text())
        if "llm" not in config_dict:
            raise ValueError("config.yaml must include an 'llm' section")
        llm_cfg = LLMConfig(**config_dict["llm"])
        game_cfg = GameConfig(**config_dict.get("game", {}))
        loop_cfg = LoopConfig(**config_dict.get("loop", {}))
        evaluation_pairs = config_dict.get("evaluation_pairs")
        return cls(llm=llm_cfg, game=game_cfg, loop=loop_cfg, evaluation_pairs=evaluation_pairs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "llm": self.llm.__dict__,
            "game": self.game.__dict__,
            "loop": self.loop.__dict__,
            "evaluation_pairs": self.evaluation_pairs,
        }
