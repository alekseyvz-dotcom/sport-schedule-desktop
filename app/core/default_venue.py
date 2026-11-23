from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import QSettings


def _settings() -> QSettings:
    return QSettings("SportApp", "Schedule")


def get_default_venue(user_id: int) -> Optional[Tuple[int, int]]:
    s = _settings()
    org_id = s.value(f"default_venue/{user_id}/org_id")
    venue_id = s.value(f"default_venue/{user_id}/venue_id")
    if org_id is None or venue_id is None:
        return None
    return int(org_id), int(venue_id)


def set_default_venue(user_id: int, org_id: int, venue_id: int) -> None:
    s = _settings()
    s.setValue(f"default_venue/{user_id}/org_id", int(org_id))
    s.setValue(f"default_venue/{user_id}/venue_id", int(venue_id))
    s.sync()
