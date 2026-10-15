"""A schedule: one line per match, independent of the solver."""

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class Fixture:
    date: dt.date
    team1: str
    team2: str
    organizer: str
