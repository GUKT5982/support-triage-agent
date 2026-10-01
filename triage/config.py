"""Runtime settings, read from environment variables (optionally via a .env file)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    model: str = "gpt-4.1-mini"
    temperature: float | None = 0.0
    max_steps: int = 6
    confidence_threshold: float = 0.7
    data_dir: Path = PROJECT_ROOT / "data"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        raw_temperature = os.getenv("TRIAGE_TEMPERATURE", "0").strip()
        return cls(
            model=os.getenv("TRIAGE_MODEL", cls.model),
            # Empty value = don't send temperature (some reasoning models reject it).
            temperature=float(raw_temperature) if raw_temperature else None,
            max_steps=int(os.getenv("TRIAGE_MAX_STEPS", cls.max_steps)),
            confidence_threshold=float(os.getenv("TRIAGE_CONFIDENCE_THRESHOLD", cls.confidence_threshold)),
            data_dir=Path(os.getenv("TRIAGE_DATA_DIR", cls.data_dir)),
        )
