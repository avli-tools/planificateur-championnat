"""Schedule export: Markdown (to read and share) and CSV (for spreadsheets)."""

import csv
import io
from pathlib import Path

from planificateur.calendrier import Fixture
from planificateur.config import Season, format_date
from planificateur.validateur import Summary

_WEEKDAYS = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")
HEADER = ("Date", "Équipe 1", "Équipe 2", "Équipe organisatrice")
MARKDOWN_TITLE = "# Calendrier — "


class OverwriteError(Exception):
    """The output path holds a file that this tool did not generate."""


def _long_date(date) -> str:
    return f"{_WEEKDAYS[date.weekday()]} {format_date(date)}"


def _table(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(" --- " for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _days(value: int | None) -> str:
    return "–" if value is None else f"{value} j"


def markdown(
    season: Season,
    fixtures: list[Fixture],
    summary: Summary,
    warnings: list[str] | None = None,
) -> str:
    lines = [f"{MARKDOWN_TITLE}{season.name}", ""]
    if warnings:
        lines += ["> ⚠️ **Calendrier provisoire** : il ne respecte pas toutes les contraintes.", ">"]
        lines += [f"> - {w}" for w in warnings]
        lines.append("")

    rows = [(_long_date(f.date), f.team1, f.team2, f.organizer) for f in fixtures]
    lines += _table(HEADER, rows)

    lines += [
        "",
        "## Résumé par équipe",
        "",
        "Un engagement, c'est jouer ou organiser une soirée.",
        "",
    ]
    rows = [
        (
            t.team,
            ", ".join(format_date(d) for d in t.matches),
            ", ".join(format_date(d) for d in t.organized),
            _days(t.engagement_gap),
            _days(t.match_gap),
        )
        for t in summary.teams
    ]
    lines += _table(
        ("Équipe", "Matchs", "Organisation", "Écart min. engagements", "Écart min. matchs"), rows
    )
    lines += [
        "",
        f"- Écart minimal entre deux engagements d'une même équipe : {_days(summary.engagement_gap)}",
        f"- Écart minimal entre deux matchs d'une même équipe : {_days(summary.match_gap)}",
        f"- Écart total à la répartition idéale des matchs : {summary.regularity:.0f} jours",
        "",
    ]
    return "\n".join(lines)


def csv_text(fixtures: list[Fixture]) -> str:
    """Semicolon-separated, as expected by spreadsheets configured in French."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(HEADER)
    for f in fixtures:
        writer.writerow((format_date(f.date), f.team1, f.team2, f.organizer))
    return buffer.getvalue()


def write(
    directory: Path,
    stem: str,
    season: Season,
    fixtures: list[Fixture],
    summary: Summary,
    warnings: list[str] | None = None,
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    md_path, csv_path = directory / f"{stem}.md", directory / f"{stem}.csv"
    _check_overwrite(md_path, MARKDOWN_TITLE)
    _check_overwrite(csv_path, ";".join(HEADER))
    md_path.write_text(markdown(season, fixtures, summary, warnings), encoding="utf-8")
    # UTF-8 with BOM so that Excel shows accents correctly.
    csv_path.write_text(csv_text(fixtures), encoding="utf-8-sig")
    return md_path, csv_path


def _check_overwrite(path: Path, expected_start: str) -> None:
    """Only replace files that this tool wrote (they start with a known header)."""
    if not path.exists():
        return
    with path.open(encoding="utf-8-sig") as file:
        start = file.read(len(expected_start))
    if start != expected_start:
        raise OverwriteError(
            f"{path} existe déjà et n'est pas un calendrier généré par cet outil : "
            "il n'a pas été modifié. Choisissez un autre dossier avec --sortie."
        )
