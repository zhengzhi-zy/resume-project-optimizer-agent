from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
NOTES_DIR = DATA_DIR / "notes"
EXPORTS_DIR = DATA_DIR / "exports"
STATIC_DIR = BASE_DIR / "static"

load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class LLMSettings:
    enabled: bool
    provider: str
    model: str
    api_key: str
    base_url: str
    temperature: float
    timeout_seconds: float


@dataclass(frozen=True)
class AppSettings:
    app_name: str
    max_questions: int
    llm: LLMSettings


def get_settings() -> AppSettings:
    return AppSettings(
        app_name=os.getenv("APP_NAME", "Resume Project Optimizer Agent"),
        max_questions=int(os.getenv("MAX_QUESTIONS", "4")),
        llm=LLMSettings(
            enabled=os.getenv("LLM_ENABLED", "false").lower() == "true",
            provider=os.getenv("LLM_PROVIDER", "deepseek"),
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            api_key=os.getenv("LLM_API_KEY", "your-key"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        ),
    )


def ensure_data_dirs() -> None:
    for path in (DATA_DIR, SESSIONS_DIR, NOTES_DIR, EXPORTS_DIR, STATIC_DIR):
        path.mkdir(parents=True, exist_ok=True)
