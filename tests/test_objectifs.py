"""Objectives: the solver must reach the same optimum as an exhaustive search."""

import itertools

import pytest
from conftest import FAST, make_season

from planificateur.calendrier import Fixture
from planificateur.resolution import solve
from planificateur.validateur import check, summarize

# Four teams, two matches each, four dates: 12^4 = 20 736 schedules to enumerate.
TINY = {
    "params": {"matchs_par_equipe": 2},
    "equipes": ["A", "B", "C", "D"],
    "dates": ["01/09/2025", "03/09/2025", "20/09/2025", "30/09/2025"],
}


def score(season, fixtures):
    """Objectives in priority order, as numbers to maximize."""
    summary = summarize(season, fixtures)
    return (
        summary.engagement_gap,
        summary.match_gap,
        sum(t.engagement_gap for t in summary.teams),
        sum(t.match_gap for t in summary.teams),
        -summary.regularity,
    )


def brute_force_best(season):
    choices = [
        (a, b, o)
        for a, b in itertools.combinations(season.teams, 2)
        for o in season.teams
        if o not in (a, b)
    ]
    best = None
    for combination in itertools.product(choices, repeat=len(season.dates)):
        fixtures = [
            Fixture(date, a, b, o)
            for date, (a, b, o) in zip(season.dates, combination, strict=True)
        ]
        if check(season, fixtures):
            continue
        s = score(season, fixtures)
        if best is None or s > best:
            best = s
    return best


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"indisponibilites": {"03/09/2025": ["A"]}},
        {"presences_imposees": {"01/09/2025": ["A"], "03/09/2025": ["B"]}},
    ],
    ids=["libre", "indisponibilite", "presences"],
)
def test_solver_matches_exhaustive_search(extra):
    season = make_season(
        TINY["params"], **{k: v for k, v in TINY.items() if k != "params"}, **extra
    )
    best = brute_force_best(season)

    result = solve(season, FAST)
    assert result.status == "optimal"
    assert check(season, result.fixtures) == []
    stages = [stage.value for stage in result.stages]
    assert stages[:4] == list(best[:4])
    assert stages[4] == pytest.approx(-best[4])
    assert score(season, result.fixtures) == pytest.approx(best)


def test_stage_values_agree_with_independent_summary():
    season = make_season()
    result = solve(season, FAST)
    summary = summarize(season, result.fixtures)
    gaps = [stage.value for stage in result.stages]
    assert summary.engagement_gap == gaps[0]
    assert summary.match_gap == gaps[1]
    assert summary.regularity == pytest.approx(gaps[4])


def test_engagement_gap_comes_first():
    # Organizing right before playing is allowed, but the solver avoids it when it can:
    # with weekly dates, the best smallest gap between engagements is 7 days.
    season = make_season()
    result = solve(season, FAST)
    assert result.stages[0].value == 7
