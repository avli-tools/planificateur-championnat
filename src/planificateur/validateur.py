"""Independent checker: verifies a schedule against a season without using the solver.

It only relies on the configuration and the list of fixtures, so it can catch
modelling mistakes in ``modele.py`` and check a schedule edited by hand.
"""

import datetime as dt
import itertools
from collections import Counter, defaultdict
from dataclasses import dataclass

from planificateur.calendrier import Fixture
from planificateur.config import Load, Season, format_date


@dataclass(frozen=True)
class TeamSummary:
    team: str
    matches: list[dt.date]
    organized: list[dt.date]
    engagement_gap: int | None  # smallest gap between two engagements, in days
    match_gap: int | None
    regularity: float  # distance in days from the ideal position of each match


@dataclass(frozen=True)
class Summary:
    teams: list[TeamSummary]

    @property
    def engagement_gap(self) -> int | None:
        return min(
            (t.engagement_gap for t in self.teams if t.engagement_gap is not None), default=None
        )

    @property
    def match_gap(self) -> int | None:
        return min((t.match_gap for t in self.teams if t.match_gap is not None), default=None)

    @property
    def regularity(self) -> float:
        return sum(t.regularity for t in self.teams)


def _smallest_gap(dates: list[dt.date]) -> int | None:
    return min(((b - a).days for a, b in itertools.pairwise(sorted(dates))), default=None)


def _load_violations(dates: list[dt.date], load: Load) -> list[list[dt.date]]:
    """Groups of ``maximum + 1`` events within fewer than ``days`` days."""
    dates = sorted(dates)
    size = load.maximum + 1
    return [
        dates[i : i + size]
        for i in range(len(dates) - size + 1)
        if (dates[i + size - 1] - dates[i]).days < load.days
    ]


def summarize(season: Season, fixtures: list[Fixture]) -> Summary:
    matches, organized = defaultdict(set), defaultdict(set)
    for f in fixtures:
        matches[f.team1].add(f.date)
        matches[f.team2].add(f.date)
        organized[f.organizer].add(f.date)

    start, length, n = season.dates[0], season.length_days, season.matches_per_team
    teams = []
    for team in season.teams:
        played = sorted(matches[team])
        regularity = sum(
            abs((date - start).days - k * length / (n + 1))
            for k, date in enumerate(played, start=1)
        )
        teams.append(
            TeamSummary(
                team=team,
                matches=played,
                organized=sorted(organized[team]),
                engagement_gap=_smallest_gap(played + sorted(organized[team])),
                match_gap=_smallest_gap(played),
                regularity=regularity,
            )
        )
    return Summary(teams)


def check(season: Season, fixtures: list[Fixture]) -> list[str]:
    """Return every rule broken by ``fixtures``, as French messages (empty if valid)."""
    problems: list[str] = []
    known = set(season.teams)
    by_date: dict[dt.date, list[Fixture]] = defaultdict(list)

    for f in fixtures:
        when = format_date(f.date)
        for name in (f.team1, f.team2, f.organizer):
            if name not in known:
                problems.append(f"{when} : équipe inconnue « {name} ».")
        if f.date not in season.dates:
            problems.append(f"{when} : cette date ne fait pas partie de la saison.")
        if f.team1 == f.team2:
            problems.append(f"{when} : {f.team1} joue contre elle-même.")
        if f.organizer in (f.team1, f.team2):
            problems.append(f"{when} : {f.organizer} organise et joue le même soir.")
        by_date[f.date].append(f)

    # One organizer per date, the right number of matches, nobody twice on a date.
    for date in season.dates:
        when, day = format_date(date), by_date.get(date, [])
        if len(day) != season.matches_per_date:
            problems.append(f"{when} : {len(day)} match(s) au lieu de {season.matches_per_date}.")
        if len({f.organizer for f in day}) > 1:
            problems.append(f"{when} : plusieurs équipes organisatrices.")
        players = Counter(team for f in day for team in (f.team1, f.team2))
        for team, count in players.items():
            if count > 1:
                problems.append(f"{when} : {team} joue {count} matchs.")

    # Pairs meet at most once; forbidden pairs never.
    meetings = Counter(frozenset((f.team1, f.team2)) for f in fixtures)
    for pair, count in meetings.items():
        a, b = sorted(pair, key=season.teams.index) if pair <= known else sorted(pair)
        if count > 1:
            problems.append(f"{a} et {b} se rencontrent {count} fois.")
    for a, b in sorted(season.forbidden_pairs):
        if meetings[frozenset((a, b))]:
            problems.append(f"{a} et {b} s'affrontent alors que c'est interdit.")

    summary = summarize(season, fixtures)
    for t in summary.teams:
        if len(t.matches) != season.matches_per_team:
            problems.append(
                f"{t.team} joue {len(t.matches)} match(s) au lieu de {season.matches_per_team}."
            )
        if len(t.organized) != season.organizations_per_team:
            problems.append(
                f"{t.team} organise {len(t.organized)} fois au lieu de "
                f"{season.organizations_per_team}."
            )
        for group in _load_violations(t.matches, season.match_load):
            problems.append(
                f"{t.team} joue {len(group)} matchs en moins de {season.match_load.days} jours : "
                + ", ".join(map(format_date, group))
                + "."
            )
        engagements = t.matches + t.organized
        for group in _load_violations(engagements, season.engagement_load):
            problems.append(
                f"{t.team} a {len(group)} engagements en moins de {season.engagement_load.days} "
                "jours : " + ", ".join(map(format_date, group)) + "."
            )
        for name, date in season.unavailable:
            if name == t.team and date in engagements:
                problems.append(
                    f"{name} est engagée le {format_date(date)} alors qu'elle est indisponible."
                )
        for name, date in season.forced:
            if name == t.team and date not in t.matches:
                problems.append(f"{name} devait jouer le {format_date(date)}.")

    for fixed in season.fixed_matches:
        a, b = fixed.teams
        day = by_date.get(fixed.date, [])
        if not any({f.team1, f.team2} == {a, b} for f in day):
            problems.append(f"Le match fixé {a} – {b} du {format_date(fixed.date)} n'y est pas.")
        if fixed.organizer and not any(f.organizer == fixed.organizer for f in day):
            problems.append(f"{fixed.organizer} devait organiser le {format_date(fixed.date)}.")

    return problems
