"""One small case that must succeed and one that must fail for each mandatory rule.

Successful schedules are always re-checked by the independent validator.
"""

from conftest import FAST, d, make_season

from planificateur.resolution import is_feasible, solve
from planificateur.validateur import check, summarize

DAILY = ["01/09/2025", "02/09/2025", "03/09/2025", "04/09/2025", "05/09/2025"]
EVERY_THIRD_DAY = [f"{day:02d}/09/2025" for day in range(1, 30, 3)]  # 10 dates
NO_MATCH_LOAD = {"charge_matchs": {"maximum": 4, "jours": 31}}


def solved(season):
    result = solve(season, FAST)
    assert result.found, result.status
    assert check(season, result.fixtures) == []
    return result.fixtures


def team(season, fixtures, name):
    return next(t for t in summarize(season, fixtures).teams if t.team == name)


# (1) Number of matches, (7) organization -------------------------------------------------


def test_every_team_plays_n_matches_and_organizes_equally():
    season = make_season()
    fixtures = solved(season)
    for t in summarize(season, fixtures).teams:
        assert len(t.matches) == 2
        assert len(t.organized) == 1
    for f in fixtures:
        assert f.organizer not in (f.team1, f.team2)


def test_organizer_must_be_a_third_team():
    # Only A and B are available on 01/09: they could play, but nobody could organize.
    season = make_season(indisponibilites={"01/09/2025": ["C", "D", "E"]})
    assert is_feasible(season, FAST) is False


def test_matches_per_date():
    season = make_season({"matchs_par_equipe": 4, "matchs_par_date": 2, **NO_MATCH_LOAD})
    fixtures = solved(season)
    assert all(sum(f.date == date for f in fixtures) == 2 for date in season.dates)


# (2) Two teams meet at most once ---------------------------------------------------------


def test_round_robin_uses_every_pair_once():
    # 5 teams x 4 matches = 10 matches = every pair exactly once.
    season = make_season({"matchs_par_equipe": 4, **NO_MATCH_LOAD}, dates=EVERY_THIRD_DAY)
    fixtures = solved(season)
    assert len({frozenset((f.team1, f.team2)) for f in fixtures}) == 10


def test_not_enough_opponents():
    # 3 teams cannot play 4 matches each without meeting twice.
    dates = ["01/09/2025", "08/09/2025", "15/09/2025", "22/09/2025", "29/09/2025", "06/10/2025"]
    season = make_season(
        {"matchs_par_equipe": 4, **NO_MATCH_LOAD},
        equipes=["A", "B", "C"],
        dates=dates,
    )
    assert is_feasible(season, FAST) is False


# (3) Unavailability ----------------------------------------------------------------------


def test_unavailable_team_neither_plays_nor_organizes():
    season = make_season(indisponibilites={"01/09/2025": ["A"], "08/09/2025": ["A"]})
    fixtures = solved(season)
    a = team(season, fixtures, "A")
    assert d("01/09/2025") not in a.matches + a.organized
    assert d("08/09/2025") not in a.matches + a.organized


def test_too_many_unavailabilities():
    # A needs 3 engagements (2 matches + 1 organization) but has only 2 free dates.
    season = make_season(
        indisponibilites={date: ["A"] for date in ["01/09/2025", "08/09/2025", "15/09/2025"]}
    )
    assert is_feasible(season, FAST) is False


# (4) Forced presence ---------------------------------------------------------------------


def test_forced_presence():
    season = make_season(presences_imposees={"15/09/2025": ["A", "C"]})
    fixtures = solved(season)
    assert {fixtures[2].team1, fixtures[2].team2} == {"A", "C"}


def test_forced_presence_on_unavailable_date():
    season = make_season(
        presences_imposees={"15/09/2025": ["A"]}, indisponibilites={"15/09/2025": ["A"]}
    )
    assert is_feasible(season, FAST) is False


def test_three_forced_teams_on_one_match():
    season = make_season(presences_imposees={"15/09/2025": ["A", "B", "C"]})
    assert is_feasible(season, FAST) is False


# (5) Forbidden pairs ---------------------------------------------------------------------


def test_forbidden_pair_never_meets():
    season = make_season(rencontres_interdites=[["A", "B"], ["A", "C"]])
    fixtures = solved(season)
    assert {"A", "B"} not in [{f.team1, f.team2} for f in fixtures]
    assert {"A", "C"} not in [{f.team1, f.team2} for f in fixtures]


def test_forbidden_pair_in_a_round_robin():
    season = make_season(
        {"matchs_par_equipe": 4, **NO_MATCH_LOAD},
        dates=EVERY_THIRD_DAY,
        rencontres_interdites=[["A", "B"]],
    )
    assert is_feasible(season, FAST) is False


# (6) Fixed matches -----------------------------------------------------------------------


def test_fixed_match_is_kept():
    season = make_season(
        matchs_fixes=[{"date": "08/09/2025", "equipes": ["B", "D"], "organisatrice": "E"}]
    )
    fixtures = solved(season)
    assert (fixtures[1].team1, fixtures[1].team2, fixtures[1].organizer) == ("B", "D", "E")


def test_all_matches_fixed_only_organizers_are_chosen():
    pairs = [["A", "B"], ["C", "D"], ["A", "E"], ["B", "C"], ["D", "E"]]
    dates = ["01/09/2025", "08/09/2025", "15/09/2025", "22/09/2025", "29/09/2025"]
    season = make_season(
        matchs_fixes=[
            {"date": date, "equipes": pair} for date, pair in zip(dates, pairs, strict=True)
        ]
    )
    fixtures = solved(season)
    assert [[f.team1, f.team2] for f in fixtures] == pairs


def test_fixed_match_with_unavailable_team():
    season = make_season(
        matchs_fixes=[{"date": "08/09/2025", "equipes": ["A", "B"]}],
        indisponibilites={"08/09/2025": ["B"]},
    )
    assert is_feasible(season, FAST) is False


# (8) Engagement load ---------------------------------------------------------------------


def test_engagement_load_respected():
    # Five consecutive days: each team has 3 engagements within 5 days.
    season = make_season({"charge_matchs": {"maximum": 2, "jours": 31}}, dates=DAILY)
    solved(season)


def test_engagement_load_too_strict():
    season = make_season({"charge_engagements": {"maximum": 2, "jours": 7}}, dates=DAILY)
    assert is_feasible(season, FAST) is False


# (9) Match load --------------------------------------------------------------------------


def test_match_load_respected():
    season = make_season({"charge_matchs": {"maximum": 1, "jours": 14}})
    fixtures = solved(season)
    for t in summarize(season, fixtures).teams:
        assert t.match_gap >= 14


def test_match_load_too_strict():
    season = make_season({"charge_matchs": {"maximum": 1, "jours": 31}})
    assert is_feasible(season, FAST) is False
