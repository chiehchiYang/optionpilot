"""Configuration with an env > defaults hierarchy (CLI flags override at call sites).

Mirrors ml-intern's config approach: environment variables override built-in defaults.
Loaded once via `Config.load()`; pass the result down rather than reading os.environ ad hoc.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    # LLM (deepseek-chat retires 2026-07-24; use the v4-flash id directly)
    model: str = "deepseek/deepseek-v4-flash"
    # Optional OpenAI-compatible endpoint (local vLLM / Ollama / LM Studio). When set, the
    # model string should be the served name, e.g. "hosted_vllm/Qwen/Qwen3-Coder-30B-A3B".
    api_base: str | None = None
    api_key: str | None = None  # for local servers any non-empty value works

    # Data
    databento_api_key: str | None = None
    data_source: str = "databento"  # which OptionDataSource to use
    thetadata_url: str = "http://127.0.0.1:25503"  # local Theta Terminal v3 (free tier)

    # Cost guard: abort a Databento fetch whose estimated cost exceeds this (USD).
    max_fetch_usd: float = 5.0

    # Paths
    cache_dir: Path = Path("./data_cache")
    runs_dir: Path = Path("./runs")

    # Agent loop
    max_iterations: int = 300
    context_compact_tokens: int = 170_000

    @classmethod
    def load(cls, dotenv: bool = True) -> "Config":
        if dotenv:
            load_dotenv()
        return cls(
            model=os.getenv("OPTIONPILOT_MODEL", cls.model),
            api_base=os.getenv("OPTIONPILOT_API_BASE") or None,
            api_key=os.getenv("OPTIONPILOT_API_KEY") or None,
            databento_api_key=os.getenv("DATABENTO_API_KEY") or None,
            data_source=os.getenv("OPTIONPILOT_DATA_SOURCE", cls.data_source),
            thetadata_url=os.getenv("OPTIONPILOT_THETADATA_URL", cls.thetadata_url),
            max_fetch_usd=float(os.getenv("OPTIONPILOT_MAX_FETCH_USD", cls.max_fetch_usd)),
            cache_dir=Path(os.getenv("OPTIONPILOT_CACHE_DIR", str(cls.cache_dir))),
            runs_dir=Path(os.getenv("OPTIONPILOT_RUNS_DIR", str(cls.runs_dir))),
        )

    def ensure_dirs(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
