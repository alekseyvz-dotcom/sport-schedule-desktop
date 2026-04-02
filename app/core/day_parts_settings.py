from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DayPartsSettings:
    morning_start: str = "06:00"
    morning_end: str = "12:00"
    day_start: str = "12:00"
    day_end: str = "18:00"
    evening_start: str = "18:00"
    evening_end: str = "23:00"

    def as_dict(self) -> dict:
        return {
            "morning_start": self.morning_start,
            "morning_end": self.morning_end,
            "day_start": self.day_start,
            "day_end": self.day_end,
            "evening_start": self.evening_start,
            "evening_end": self.evening_end,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "DayPartsSettings":
        data = data or {}
        return cls(
            morning_start=str(data.get("morning_start", "06:00")),
            morning_end=str(data.get("morning_end", "12:00")),
            day_start=str(data.get("day_start", "12:00")),
            day_end=str(data.get("day_end", "18:00")),
            evening_start=str(data.get("evening_start", "18:00")),
            evening_end=str(data.get("evening_end", "23:00")),
        )

    def to_display_text(self) -> str:
        return (
            f"Утро {self.morning_start}–{self.morning_end}  |  "
            f"День {self.day_start}–{self.day_end}  |  "
            f"Вечер {self.evening_start}–{self.evening_end}"
        )
