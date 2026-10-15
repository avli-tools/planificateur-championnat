"""CP-SAT model of a season: variables, mandatory constraints and objective terms.

Notation: ``t`` indexes teams, ``d`` dates, ``p`` unordered pairs of teams.
An *engagement* is playing or organizing on a date.
"""

import itertools
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from planificateur.config import Season, format_date


@dataclass
class SoftConstraint:
    """A local constraint that the diagnostic may drop; ``kept`` is true when it holds."""

    kind: str  # "indisponibilite", "presence", "rencontre_interdite", "match_fixe"
    item: object  # the (team, date), pair or FixedMatch from the Season
    description: str
    kept: cp_model.IntVar

    @property
    def key(self) -> tuple[str, object]:
        return (self.kind, self.item)


@dataclass
class MinGap:
    """Smallest gap in days between two events of a same team: overall and per team."""

    overall: cp_model.IntVar
    per_team: list[cp_model.IntVar]


@dataclass
class SeasonModel:
    season: Season
    model: cp_model.CpModel
    days: list[int]  # day number of each date, relative to the first date
    pairs: list[tuple[int, int]]
    match: dict[tuple[int, int], cp_model.IntVar]  # (p, d)
    plays: dict[tuple[int, int], cp_model.IntVar]  # (t, d)
    organizes: dict[tuple[int, int], cp_model.IntVar]  # (t, d)
    soft: list[SoftConstraint] = field(default_factory=list)
    # Objective terms, filled by add_objectives().
    engagement_gap: MinGap | None = None
    match_gap: MinGap | None = None
    regularity_cost: cp_model.LinearExpr | None = None

    @property
    def n_teams(self) -> int:
        return len(self.season.teams)

    @property
    def n_dates(self) -> int:
        return len(self.season.dates)

    def windows(self, length: int) -> list[list[int]]:
        """For each date, the dates that fall less than ``length`` days after it (itself included).

        Any two dates closer than ``length`` days belong to a common window, so
        "at most one per window" is exactly "no two closer than ``length`` days".
        """
        result = []
        for start in range(self.n_dates):
            window = [
                d for d in range(start, self.n_dates) if self.days[d] - self.days[start] < length
            ]
            if len(window) > 1:
                result.append(window)
        return result


def build(season: Season, relax_local: bool = False) -> SeasonModel:
    """Build the model with every mandatory constraint.

    With ``relax_local``, the local constraints (unavailability, forced presence,
    forbidden or required pair, fixed match) are only enforced when their ``kept`` literal is
    true, so that the diagnostic can find which ones to drop.
    """
    model = cp_model.CpModel()
    teams, dates = season.teams, season.dates
    n_teams, n_dates = len(teams), len(dates)
    team_index = {name: t for t, name in enumerate(teams)}
    date_index = {date: d for d, date in enumerate(dates)}
    days = [(date - dates[0]).days for date in dates]
    pairs = list(itertools.combinations(range(n_teams), 2))
    pair_index = {pair: p for p, pair in enumerate(pairs)}

    match = {
        (p, d): model.new_bool_var(f"match_{a}_{b}_{d}")
        for p, (a, b) in enumerate(pairs)
        for d in range(n_dates)
    }
    plays = {
        (t, d): model.new_bool_var(f"plays_{t}_{d}") for t in range(n_teams) for d in range(n_dates)
    }
    organizes = {
        (t, d): model.new_bool_var(f"organizes_{t}_{d}")
        for t in range(n_teams)
        for d in range(n_dates)
    }
    sm = SeasonModel(season, model, days, pairs, match, plays, organizes)

    # Link: a team plays on a date iff one of its pairs plays then (at most one match per team).
    for t in range(n_teams):
        own = [p for p, pair in enumerate(pairs) if t in pair]
        for d in range(n_dates):
            model.add(plays[t, d] == sum(match[p, d] for p in own))

    for d in range(n_dates):
        model.add(sum(match[p, d] for p in range(len(pairs))) == season.matches_per_date)
        # (7) One organizer per date, who does not play that evening.
        model.add_exactly_one(organizes[t, d] for t in range(n_teams))
        for t in range(n_teams):
            model.add_at_most_one(plays[t, d], organizes[t, d])

    for t in range(n_teams):
        # (1) Exactly N matches.
        model.add(sum(plays[t, d] for d in range(n_dates)) == season.matches_per_team)
        # (7) Every team organizes the same number of times.
        model.add(sum(organizes[t, d] for d in range(n_dates)) == season.organizations_per_team)
        # (8) Engagement load: at most M engagements in any period of P days.
        load = season.engagement_load
        for window in sm.windows(load.days):
            if len(window) > load.maximum:
                model.add(sum(plays[t, d] + organizes[t, d] for d in window) <= load.maximum)
        # (9) Match load: at most M matches in any period of P days.
        load = season.match_load
        for window in sm.windows(load.days):
            if len(window) > load.maximum:
                model.add(sum(plays[t, d] for d in window) <= load.maximum)

    # (2) Two teams meet at most once.
    for p in range(len(pairs)):
        model.add(sum(match[p, d] for d in range(n_dates)) <= 1)

    def local(kind: str, item: object, description: str):
        """Enforcement literals for a local constraint (none when it is hard)."""
        if not relax_local:
            return []
        kept = model.new_bool_var(f"kept_{len(sm.soft)}")
        sm.soft.append(SoftConstraint(kind, item, description, kept))
        return [kept]

    # (3) Unavailability: neither play nor organize.
    for name, date in sorted(season.unavailable, key=lambda x: (x[1], team_index[x[0]])):
        t, d = team_index[name], date_index[date]
        enforce = local(
            "indisponibilite", (name, date), f"{name} indisponible le {format_date(date)}"
        )
        model.add(plays[t, d] + organizes[t, d] == 0).only_enforce_if(enforce)

    # (4) Forced presence: must play.
    for name, date in sorted(season.forced, key=lambda x: (x[1], team_index[x[0]])):
        t, d = team_index[name], date_index[date]
        enforce = local("presence", (name, date), f"{name} doit jouer le {format_date(date)}")
        model.add(plays[t, d] == 1).only_enforce_if(enforce)

    # (5) Forbidden pairs never meet.
    for a, b in sorted(season.forbidden_pairs, key=lambda x: (team_index[x[0]], team_index[x[1]])):
        p = pair_index[team_index[a], team_index[b]]
        enforce = local("rencontre_interdite", (a, b), f"{a} et {b} ne doivent pas s'affronter")
        model.add(sum(match[p, d] for d in range(n_dates)) == 0).only_enforce_if(enforce)

    # (5b) Required pairs meet once, on a date chosen by the solver.
    for a, b in sorted(season.required_pairs, key=lambda x: (team_index[x[0]], team_index[x[1]])):
        p = pair_index[team_index[a], team_index[b]]
        enforce = local("rencontre_imposee", (a, b), f"{a} et {b} doivent s'affronter")
        model.add(sum(match[p, d] for d in range(n_dates)) == 1).only_enforce_if(enforce)

    # (6) Fixed matches (and organizer, if given).
    for fixed in season.fixed_matches:
        a, b = fixed.teams
        p, d = pair_index[team_index[a], team_index[b]], date_index[fixed.date]
        description = f"match fixé {a} – {b} le {format_date(fixed.date)}"
        if fixed.organizer:
            description += f" (organisation : {fixed.organizer})"
        enforce = local("match_fixe", fixed, description)
        model.add(match[p, d] == 1).only_enforce_if(enforce)
        if fixed.organizer:
            model.add(organizes[team_index[fixed.organizer], d] == 1).only_enforce_if(enforce)

    return sm


def add_objectives(sm: SeasonModel) -> None:
    """Create the objective terms (the solver sets the objective itself, stage by stage).

    - ``engagement_gap``: smallest gap, in days, between two engagements of a team
      (overall, and per team so that their sum can be maximized as a tie-break);
    - ``match_gap``: the same for matches only;
    - ``regularity_cost``: distance between each match and its ideal position.
    """
    season = sm.season
    engagements = _sequence(
        sm, lambda t, d: sm.plays[t, d] + sm.organizes[t, d], season.engagements_per_team, "eng"
    )
    matches = _sequence(sm, lambda t, d: sm.plays[t, d], season.matches_per_team, "match")
    sm.engagement_gap = _min_gap(sm, engagements, "engagement")
    sm.match_gap = _min_gap(sm, matches, "match")

    # Regularity: the k-th match (k = 1..N) ideally falls at k * L / (N + 1) days from the start.
    # Costs are scaled by (N + 1) to stay integral: cost = |(N + 1) * day - k * L|.
    n_matches, length = season.matches_per_team, season.length_days
    sm.regularity_cost = sum(
        abs((n_matches + 1) * sm.days[d] - (k + 1) * length) * literal
        for ranks in matches.ranks
        for (d, k), literal in ranks.items()
    )


@dataclass
class _Sequence:
    """Events of each team in chronological order."""

    ranks: list[dict[tuple[int, int], cp_model.IntVar]]  # per team: (d, k) <=> k-th event on d
    days: list[list[cp_model.IntVar]]  # per team: day number of the k-th event


def _sequence(sm: SeasonModel, event, count: int, name: str) -> _Sequence:
    """Number the ``count`` events of each team: ``event(t, d)`` is 1 if t has one on date d."""
    model, n_dates = sm.model, sm.n_dates
    sequence = _Sequence([], [])
    for t in range(sm.n_teams):
        ranks = {}
        before = model.new_constant(0)  # number of events of t strictly before d
        for d in range(n_dates):
            # The k-th event (0-based) needs k earlier dates and count - k - 1 later ones.
            possible = range(max(0, count - (n_dates - d)), min(count, d + 1))
            here = []
            for k in possible:
                rank = model.new_bool_var(f"{name}_rank_{t}_{d}_{k}")
                model.add(before == k).only_enforce_if(rank)
                ranks[d, k] = rank
                here.append(rank)
            model.add(sum(here) == event(t, d))
            after = model.new_int_var(0, count, f"{name}_count_{t}_{d}")
            model.add(after == before + event(t, d))
            before = after
        days = []
        for k in range(count):
            model.add_exactly_one(lit for (d, j), lit in ranks.items() if j == k)
            day = model.new_int_var(0, sm.days[-1], f"{name}_day_{t}_{k}")
            model.add(day == sum(sm.days[d] * lit for (d, j), lit in ranks.items() if j == k))
            days.append(day)
        sequence.ranks.append(ranks)
        sequence.days.append(days)
    return sequence


def _min_gap(sm: SeasonModel, sequence: _Sequence, name: str) -> MinGap:
    """Smallest gap between two consecutive events, per team and overall."""
    model, horizon = sm.model, sm.days[-1]
    per_team = []
    for t, days in enumerate(sequence.days):
        gap = model.new_int_var(0, horizon, f"{name}_gap_{t}")
        if len(days) < 2:
            model.add(gap == 0)
        else:
            model.add_min_equality(gap, [b - a for a, b in itertools.pairwise(days)])
        per_team.append(gap)
    overall = model.new_int_var(0, horizon, f"{name}_gap")
    model.add_min_equality(overall, per_team)
    return MinGap(overall, per_team)
