import datetime as dt
from pathlib import Path

import pytest
from conftest import d, make_data, make_season

from planificateur import config

ROOT = Path(__file__).parent.parent


def errors_of(data) -> list[str]:
    with pytest.raises(config.ConfigError) as exc:
        config.parse(data)
    return exc.value.errors


def test_example_file_loads():
    season = config.load(ROOT / "exemples" / "saison-exemple.yaml")
    assert len(season.teams) == 11
    assert len(season.dates) == 22
    assert season.matches_per_team == 4
    assert season.organizations_per_team == 2
    assert season.match_load == config.Load(2, 31)
    assert season.engagement_load == config.Load(3, 7)
    assert ("Équipe A", d("27/11/2025")) in season.unavailable
    assert ("Équipe C", d("29/01/2026")) in season.forced


def test_minimal_season_and_defaults():
    season = make_season()
    assert season.matches_per_date == 1
    assert season.organizations_per_team == 1  # 5 dates / 5 teams
    assert season.length_days == 28


def test_unknown_team_suggests_closest_name():
    data = make_data(equipes=["La Fanfare", "B", "C", "D", "E"])
    data["indisponibilites"] = {"01/09/2025": ["la fanfare"]}
    (error,) = errors_of(data)
    assert "« la fanfare »" in error
    assert "Vouliez-vous dire « La Fanfare » ?" in error
    assert "indisponibilites › 01/09/2025" in error


def test_unknown_team_in_every_section():
    data = make_data(
        presences_imposees={"01/09/2025": ["Z"]},
        rencontres_interdites=[["A", "Y"]],
        matchs_fixes=[{"date": "08/09/2025", "equipes": ["X", "B"]}],
    )
    errors = errors_of(data)
    assert len(errors) == 3
    assert all("Équipe inconnue" in e for e in errors)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1/9/2025", "Date mal formée « 1/9/2025 »"),
        ("31/02/2025", "Date inexistante « 31/02/2025 »"),
        ("02/09/2025", "ne fait pas partie des dates de la saison"),
    ],
)
def test_bad_dates(value, expected):
    (error,) = errors_of(make_data(indisponibilites={value: ["A"]}))
    assert expected in error


def test_iso_date_gets_a_hint():
    data = make_data()
    data["dates"][0] = dt.date(2025, 9, 1)  # what YAML gives for an unquoted 2025-09-01
    errors = errors_of(data)
    assert any("format JJ/MM/AAAA" in e and "« 01/09/2025 »" in e for e in errors)


def test_duplicate_date_and_team():
    data = make_data(equipes=["A", "B", "C", "D", "E", "A"])
    data["dates"].append("01/09/2025")
    errors = errors_of(data)
    assert any("Équipe « A » déclarée deux fois" in e for e in errors)
    assert any("présente deux fois" in e for e in errors)


def test_unknown_key_suggests_closest():
    data = make_data()
    data["indisponibilités"] = {}
    (error,) = errors_of(data)
    assert "Vouliez-vous dire « indisponibilites » ?" in error


def test_missing_sections_and_parameters():
    errors = errors_of({"equipes": ["A", "B", "C"]})
    assert "Section obligatoire manquante : « parametres »." in errors
    assert "Section obligatoire manquante : « dates »." in errors
    errors = errors_of(make_data(parametres={"matchs_par_equipe": 2}))
    assert any("charge_matchs" in e for e in errors)


def test_inconsistent_parameters():
    (error,) = errors_of(make_data({"matchs_par_equipe": 3}))
    assert "Paramètres incohérents" in error
    (error,) = errors_of(make_data({"organisations_par_equipe": 2}))
    assert "organisations" in error


def test_load_must_be_complete():
    (error,) = errors_of(make_data({"charge_matchs": {"maximum": 2}}))
    assert "charge_matchs › jours" in error


def test_fixed_match_errors():
    errors = errors_of(
        make_data(
            matchs_fixes=[
                {"date": "01/09/2025", "equipes": ["A", "A"]},
                {"date": "08/09/2025", "equipes": ["A", "B"], "organisatrice": "B"},
                {"date": "15/09/2025", "equipes": ["C", "D"]},
                {"date": "22/09/2025", "equipes": ["D", "C"]},
            ]
        )
    )
    assert any("s'affronter elle-même" in e for e in errors)
    assert any("ne peut pas jouer ce match" in e for e in errors)
    assert any("fixé deux fois" in e for e in errors)


def test_pairs_are_stored_in_declaration_order():
    season = make_season(
        rencontres_interdites=[["C", "A"]],
        matchs_fixes=[{"date": "01/09/2025", "equipes": ["E", "B"]}],
    )
    assert season.forbidden_pairs == {("A", "C")}
    assert season.fixed_matches[0].teams == ("B", "E")


def test_yaml_file_errors(tmp_path):
    with pytest.raises(config.ConfigError, match="introuvable"):
        config.load(tmp_path / "absent.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("equipes: [A, B\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match="illisible"):
        config.load(bad)


def test_duplicate_yaml_key_is_an_error(tmp_path):
    path = tmp_path / "saison.yaml"
    path.write_text("indisponibilites:\n  01/09/2025: [A]\n  01/09/2025: [B]\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match="répétée"):
        config.load(path)


def test_required_pairs():
    season = make_season(rencontres_imposees=[["C", "A"]])
    assert season.required_pairs == {("A", "C")}
    data = make_data(rencontres_imposees=[["A", "Équipe Z"]])
    (error,) = errors_of(data)
    assert "« rencontres_imposees » (n° 1)" in error
