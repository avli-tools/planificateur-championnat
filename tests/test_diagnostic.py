from dataclasses import replace
from pathlib import Path

from conftest import FAST, make_season

from planificateur import config, diagnostic
from planificateur.validateur import check

ROOT = Path(__file__).parent.parent
DAILY = ["01/09/2025", "02/09/2025", "03/09/2025", "04/09/2025", "05/09/2025"]


def test_quick_checks_on_a_feasible_season():
    assert diagnostic.quick_checks(make_season()) == []


def test_quick_checks_find_local_contradictions():
    season = make_season(
        indisponibilites={
            "01/09/2025": ["C", "D", "E"],
            "08/09/2025": ["B"],
            "15/09/2025": ["B"],
            "22/09/2025": ["B"],
        },
        presences_imposees={"08/09/2025": ["B"]},
        matchs_fixes=[{"date": "29/09/2025", "equipes": ["A", "C"]}],
        rencontres_interdites=[["A", "C"]],
    )
    checks = diagnostic.quick_checks(season)
    assert any("Le 01/09/2025, seules 2 équipes sont disponibles" in c for c in checks)
    assert any("B n'est disponible qu'à 2 dates" in c for c in checks)
    assert any("B doit jouer le 08/09/2025, mais y est indisponible" in c for c in checks)
    assert any("est une rencontre interdite" in c for c in checks)


def test_quick_checks_find_packed_dates():
    # The anonymized example with the old "one engagement per 7 days" rule: the four dates
    # from 29/01 to 03/02/2026 need 12 engagements but there are only 11 teams.
    season = config.load(ROOT / "exemples" / "saison-exemple.yaml")
    strict = replace(season, engagement_load=config.Load(1, 7))
    checks = diagnostic.quick_checks(strict)
    assert any("du 29/01/2026 au 03/02/2026" in c and "12 engagements" in c for c in checks)


def test_minimal_relaxation_finds_the_culprits():
    # Only A and B are free on 01/09: freeing any one of C, D, E is enough.
    season = make_season(indisponibilites={"01/09/2025": ["C", "D", "E"], "15/09/2025": ["A"]})
    options = diagnostic.minimal_relaxations(season, FAST)
    assert len(options) == 3
    assert all(len(option) == 1 for option in options)
    culprits = {option[0].description for option in options}
    assert culprits == {f"{t} indisponible le 01/09/2025" for t in "CDE"}


def test_diagnose_gives_a_valid_fallback():
    season = make_season(indisponibilites={"01/09/2025": ["C", "D", "E"]})
    diagnosis = diagnostic.diagnose(season, FAST)
    assert diagnosis.fallback is not None and diagnosis.fallback.found
    relaxed = diagnostic.without(season, diagnosis.options[0])
    assert check(relaxed, diagnosis.fallback.fixtures) == []
    text = diagnostic.report(diagnosis)
    assert "Il suffit d'ignorer 1 contrainte." in text
    assert "indisponible le 01/09/2025" in text


def test_structural_problem():
    # Five consecutive days and at most two engagements per week: no local constraint to drop.
    season = make_season({"charge_engagements": {"maximum": 2, "jours": 7}}, dates=DAILY)
    diagnosis = diagnostic.diagnose(season, FAST)
    assert diagnosis.options == []
    assert diagnosis.structural == [
        "Possible avec « charge_engagements › maximum » = 3 au lieu de 2 (sur 7 jours)."
    ]
    assert "trop contraignants" in diagnostic.report(diagnosis)
