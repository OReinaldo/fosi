"""Stable FOSI schema helpers for normalized team scouting data."""
from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class Match:
    id: str
    date: str | None = None
    opponent: str | None = None
    venue: str | None = None
    result: str | None = None
    goals_for: float | None = None
    goals_against: float | None = None

@dataclass
class TeamSnapshot:
    team_id: str
    team_name: str
    competition: str
    matches: list[dict[str, Any]]
    players: list[dict[str, Any]]
    metrics: dict[str, Any]

    def to_dict(self):
        return asdict(self)
