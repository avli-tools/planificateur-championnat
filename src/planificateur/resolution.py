"""Lexicographic solving: each objective is optimized, then frozen, before the next one."""

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from planificateur import modele
from planificateur.calendrier import Fixture
from planificateur.config import Season


@dataclass(frozen=True)
class Stage:
    label: str
    value: float
    proven: bool  # True when the solver proved this value optimal


@dataclass
class Result:
    status: str  # "optimal", "faisable", "impossible" or "inconnu"
    fixtures: list[Fixture] = field(default_factory=list)
    stages: list[Stage] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.status in ("optimal", "faisable")


@dataclass(frozen=True)
class Options:
    time_limit: float = 30.0  # seconds, per stage
    seed: int = 0
    workers: int = 0  # 0: all available cores


def make_solver(options: Options) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = options.time_limit
    solver.parameters.random_seed = options.seed
    solver.parameters.num_workers = options.workers
    return solver


def extract(sm: modele.SeasonModel, solver: cp_model.CpSolver) -> list[Fixture]:
    season = sm.season
    fixtures = []
    for d, date in enumerate(season.dates):
        organizer = next(
            season.teams[t] for t in range(sm.n_teams) if solver.value(sm.organizes[t, d])
        )
        for p, (a, b) in enumerate(sm.pairs):
            if solver.value(sm.match[p, d]):
                fixtures.append(Fixture(date, season.teams[a], season.teams[b], organizer))
    return fixtures


def _hint(sm: modele.SeasonModel, solver: cp_model.CpSolver) -> None:
    sm.model.clear_hints()
    for var in list(sm.match.values()) + list(sm.organizes.values()):
        sm.model.add_hint(var, solver.value(var))


def solve(season: Season, options: Options | None = None) -> Result:
    """Find the best schedule, optimizing the objectives one after the other (see README)."""
    options = options or Options()
    sm = modele.build(season)
    modele.add_objectives(sm)
    scale = season.matches_per_team + 1  # regularity costs are scaled, see add_objectives()

    stages = [
        # Smallest gaps first, then the per-team sums as tie-breaks.
        ("Écart minimal entre deux engagements (jours)", sm.engagement_gap.overall, True, 1),
        ("Écart minimal entre deux matchs (jours)", sm.match_gap.overall, True, 1),
        (
            "Somme des écarts minimaux entre engagements, par équipe (jours)",
            sum(sm.engagement_gap.per_team),
            True,
            1,
        ),
        (
            "Somme des écarts minimaux entre matchs, par équipe (jours)",
            sum(sm.match_gap.per_team),
            True,
            1,
        ),
        ("Écart total à la répartition idéale (jours)", sm.regularity_cost, False, scale),
    ]
    result = Result(status="optimal")
    for label, expr, maximize, divisor in stages:
        if maximize:
            sm.model.maximize(expr)
        else:
            sm.model.minimize(expr)
        solver = make_solver(options)
        status = solver.solve(sm.model)
        if status == cp_model.INFEASIBLE:
            return Result(status="impossible")
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if not result.fixtures:
                return Result(status="inconnu")
            result.status = "faisable"  # keep the previous stage's schedule
            break
        value = round(solver.objective_value)
        proven = status == cp_model.OPTIMAL
        if not proven:
            result.status = "faisable"
        result.stages.append(Stage(label, value / divisor, proven))
        result.fixtures = extract(sm, solver)
        # Freeze this objective before optimizing the next one.
        sm.model.add(expr >= value if maximize else expr <= value)
        _hint(sm, solver)
    return result


def is_feasible(season: Season, options: Options | None = None) -> bool | None:
    """True / False, or None when the time limit is reached without an answer."""
    sm = modele.build(season)
    status = make_solver(options or Options()).solve(sm.model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return True
    return False if status == cp_model.INFEASIBLE else None
