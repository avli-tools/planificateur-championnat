"""The independent checker must itself catch every kind of broken rule."""

from dataclasses import replace

import pytest
from conftest import d, make_season

from planificateur.calendrier import Fixture
from planificateur.validateur import check, summarize

# A valid hand-made schedule for the base season (5 teams, 2 matches, 1 organization each).
VALID = [
    Fixture(d("01/09/2025"), "A", "B", "E"),
    Fixture(d("08/09/2025"), "C", "D", "A"),
    Fixture(d("15/09/2025"), "A", "E", "B"),
    Fixture(d("22/09/2025"), "B", "C", "D"),
    Fixture(d("29/09/2025"), "D", "E", "C"),
]


def with_line(index: int, **changes) -> list[Fixture]:
    fixtures = list(VALID)
    fixtures[index] = replace(fixtures[index], **changes)
    return fixtures


def test_valid_schedule_passes():
    assert check(make_season(), VALID) == []


def test_summary():
    summary = summarize(make_season(), VALID)
    a = summary.teams[0]
    assert a.matches == [d("01/09/2025"), d("15/09/2025")]
    assert a.organized == [d("08/09/2025")]
    assert a.engagement_gap == 7
    assert a.match_gap == 14
    assert summary.engagement_gap == 7
    assert summary.match_gap == 14
    # Season of 28 days, 2 matches: ideal positions at 28/3 and 56/3 days.
    assert a.regularity == pytest.approx(abs(0 - 28 / 3) + abs(14 - 56 / 3))


@pytest.mark.parametrize(
    ("fixtures", "expected"),
    [
        (with_line(0, organizer="A"), "A organise et joue le même soir"),
        (with_line(0, team2="Z"), "équipe inconnue « Z »"),
        (with_line(0, date=d("02/09/2025")), "ne fait pas partie de la saison"),
        (VALID[:4], "0 match(s) au lieu de 1"),
        (with_line(4, team1="A", team2="B"), "A et B se rencontrent 2 fois"),
        (with_line(4, team1="A", team2="B"), "A joue 3 match(s) au lieu de 2"),
        (with_line(4, organizer="E"), "E organise et joue le même soir"),
        (with_line(4, organizer="A"), "A organise 2 fois au lieu de 1"),
    ],
)
def test_structural_violations(fixtures, expected):
    assert any(expected in p for p in check(make_season(), fixtures)), check(
        make_season(), fixtures
    )


def test_unavailability_violation():
    season = make_season(indisponibilites={"08/09/2025": ["A"]})  # A organizes that day
    assert check(season, VALID) == ["A est engagée le 08/09/2025 alors qu'elle est indisponible."]


def test_forced_presence_violation():
    season = make_season(presences_imposees={"08/09/2025": ["E"]})
    assert check(season, VALID) == ["E devait jouer le 08/09/2025."]


def test_forbidden_pair_violation():
    season = make_season(rencontres_interdites=[["B", "A"]])
    assert check(season, VALID) == ["A et B s'affrontent alors que c'est interdit."]


def test_fixed_match_violations():
    season = make_season(
        matchs_fixes=[
            {"date": "01/09/2025", "equipes": ["A", "C"]},
            {"date": "08/09/2025", "equipes": ["C", "D"], "organisatrice": "B"},
        ]
    )
    problems = check(season, VALID)
    assert "Le match fixé A – C du 01/09/2025 n'y est pas." in problems
    assert "B devait organiser le 08/09/2025." in problems


def test_match_load_violation():
    season = make_season({"charge_matchs": {"maximum": 1, "jours": 15}})
    problems = check(season, VALID)
    # A plays on 01/09 and 15/09 (14 days apart): two matches in fewer than 15 days.
    assert "A joue 2 matchs en moins de 15 jours : 01/09/2025, 15/09/2025." in problems


def test_engagement_load_violation():
    season = make_season({"charge_engagements": {"maximum": 1, "jours": 8}})
    problems = check(season, VALID)
    assert "A a 2 engagements en moins de 8 jours : 01/09/2025, 08/09/2025." in problems
    assert check(make_season({"charge_engagements": {"maximum": 1, "jours": 7}}), VALID) == []


def test_required_pair_violation():
    season = make_season(rencontres_imposees=[["C", "A"], ["A", "B"]])
    assert check(season, VALID) == ["A et C devaient s'affronter."]
