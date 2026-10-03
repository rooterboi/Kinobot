"""Sozlamalar (.env dan o'qiladi)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _parse_ids(raw: str) -> tuple[int, ...]:
    ids = []
    for part in raw.replace(" ", "").split(","):
        if part.lstrip("-").isdigit():
            ids.append(int(part))
    return tuple(ids)


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: tuple[int, ...]
    db_path: str = "data/kino.db"
    default_pin: str = "9767"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN .env faylida ko'rsatilmagan!")
    admin_ids = _parse_ids(os.getenv("ADMIN_IDS", ""))
    if not admin_ids:
        raise RuntimeError("ADMIN_IDS .env faylida ko'rsatilmagan!")
    return Config(
        bot_token=token,
        admin_ids=admin_ids,
        db_path=os.getenv("DB_PATH", "data/kino.db").strip(),
        default_pin=os.getenv("DEFAULT_PIN", "9767").strip(),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
    )
