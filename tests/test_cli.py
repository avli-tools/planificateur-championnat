import shutil
from pathlib import Path

import pytest

from planificateur.cli import IMPOSSIBLE, INVALID_CONFIG, OK, OUTPUT_ERROR, main

ROOT = Path(__file__).parent.parent
SMALL = """\
saison: Petite saison
equipes: [A, B, C, D, E]
parametres:
  matchs_par_equipe: 2
  charge_matchs: {maximum: 2, jours: 31}
  charge_engagements: {maximum: 3, jours: 7}
dates: [01/09/2025, 08/09/2025, 15/09/2025, 22/09/2025, 29/09/2025]
"""


@pytest.fixture
def small(tmp_path):
    path = tmp_path / "petite.yaml"
    path.write_text(SMALL, encoding="utf-8")
    return path


def test_help_exits_cleanly():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_writes_schedule_next_to_the_config(small, capsys):
    assert main([str(small), "-t", "5"]) == OK
    assert (small.parent / "petite-calendrier.md").exists()
    assert (small.parent / "petite-calendrier.csv").exists()
    out = capsys.readouterr().out
    assert "| Date | Équipe 1 | Équipe 2 | Équipe organisatrice |" in out
    assert "(optimal)" in out


def test_output_directory_option(small, tmp_path):
    out = tmp_path / "sortie"
    assert main([str(small), "-t", "5", "--sortie", str(out)]) == OK
    assert (out / "petite-calendrier.csv").exists()


def test_never_overwrites_season_notes(small):
    notes = small.parent / "petite-calendrier.md"
    notes.write_text("Mes notes\n", encoding="utf-8")
    assert main([str(small), "-t", "5"]) == OUTPUT_ERROR
    assert notes.read_text(encoding="utf-8") == "Mes notes\n"


def test_invalid_config(small, capsys):
    small.write_text(SMALL + "indisponibilites:\n  01/09/2025: [a]\n", encoding="utf-8")
    assert main([str(small)]) == INVALID_CONFIG
    err = capsys.readouterr().err
    assert "Configuration invalide" in err
    assert "Vouliez-vous dire « A » ?" in err


def test_impossible_season_writes_a_provisional_schedule(small, capsys):
    small.write_text(SMALL + "indisponibilites:\n  01/09/2025: [C, D, E]\n", encoding="utf-8")
    assert main([str(small), "-t", "5"]) == IMPOSSIBLE
    out = capsys.readouterr().out
    assert "Aucun calendrier ne respecte toutes les contraintes." in out
    provisional = small.parent / "petite-calendrier-provisoire.md"
    assert "Calendrier provisoire" in provisional.read_text(encoding="utf-8")


def test_example_season(tmp_path):
    """The anonymized example: the CLI re-checks the schedule with the independent validator."""
    config = tmp_path / "saison-exemple.yaml"
    shutil.copy(ROOT / "exemples" / "saison-exemple.yaml", config)
    assert main([str(config), "-t", "2"]) == OK
    csv = (tmp_path / "saison-exemple-calendrier.csv").read_text(encoding="utf-8-sig")
    assert len(csv.splitlines()) == 23
