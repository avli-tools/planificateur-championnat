import pytest
from conftest import make_season
from test_validateur import VALID

from planificateur import export
from planificateur.validateur import summarize


def test_markdown_table_and_summary():
    season = make_season()
    text = export.markdown(season, VALID, summarize(season, VALID))
    assert text.startswith("# Calendrier — Test")
    assert "| Date | Équipe 1 | Équipe 2 | Équipe organisatrice |" in text
    assert "| lun. 01/09/2025 | A | B | E |" in text
    assert "| A | 01/09/2025, 15/09/2025 | 08/09/2025 | 7 j | 14 j |" in text
    assert "Calendrier provisoire" not in text


def test_markdown_warnings():
    season = make_season()
    text = export.markdown(season, VALID, summarize(season, VALID), ["Ignoré : X."])
    assert "Calendrier provisoire" in text
    assert "> - Ignoré : X." in text


def test_csv():
    lines = export.csv_text(VALID).splitlines()
    assert lines[0] == "Date;Équipe 1;Équipe 2;Équipe organisatrice"
    assert lines[1] == "01/09/2025;A;B;E"
    assert len(lines) == 6


def test_write_files_with_bom_and_overwrite_own_files(tmp_path):
    season = make_season()
    summary = summarize(season, VALID)
    md, csv = export.write(tmp_path, "test-calendrier", season, VALID, summary)
    assert csv.read_bytes().startswith(b"\xef\xbb\xbf")  # UTF-8 BOM for Excel
    assert md.read_text(encoding="utf-8").startswith("# Calendrier")
    export.write(tmp_path, "test-calendrier", season, VALID, summary)  # regenerating is fine


def test_never_overwrites_a_foreign_file(tmp_path):
    season = make_season()
    foreign = tmp_path / "saison.md"
    foreign.write_text("# Mes notes de saison\n", encoding="utf-8")
    with pytest.raises(export.OverwriteError):
        export.write(tmp_path, "saison", season, VALID, summarize(season, VALID))
    assert foreign.read_text(encoding="utf-8") == "# Mes notes de saison\n"
    assert not (tmp_path / "saison.csv").exists()
