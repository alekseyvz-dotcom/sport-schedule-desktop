from __future__ import annotations

import json
from pathlib import Path

from app.core.day_parts_settings import DayPartsSettings


_SETTINGS_FILE = Path("settings.dat")
_SETTINGS_KEY = "day_parts"


def _load_all_settings() -> dict:
    if not _SETTINGS_FILE.exists():
        return {}

    try:
        with _SETTINGS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_all_settings(data: dict) -> None:
    with _SETTINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_day_parts_settings() -> DayPartsSettings:
    data = _load_all_settings()
    return DayPartsSettings.from_dict(data.get(_SETTINGS_KEY))


def save_day_parts_settings(settings: DayPartsSettings) -> None:
    data = _load_all_settings()
    data[_SETTINGS_KEY] = settings.as_dict()
    _save_all_settings(data)


def get_default_day_parts_settings() -> DayPartsSettings:
    return DayPartsSettings()
