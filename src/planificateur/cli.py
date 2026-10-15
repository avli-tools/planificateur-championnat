"""Command-line entry point: ``planificateur saisons/2026-2027.yaml``."""

import argparse
import sys
from pathlib import Path

from planificateur import config, diagnostic, export, validateur
from planificateur.resolution import Options, Result, solve

# Exit codes.
OK, IMPOSSIBLE, INVALID_CONFIG, INTERNAL_ERROR, NO_ANSWER, OUTPUT_ERROR = 0, 1, 2, 3, 4, 5


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="planificateur",
        description="Génère le calendrier d'une saison à partir d'un fichier YAML.",
    )
    parser.add_argument("config", type=Path, help="fichier YAML de la saison")
    parser.add_argument(
        "-s",
        "--sortie",
        type=Path,
        help="dossier où écrire le calendrier (par défaut : celui du fichier YAML)",
    )
    parser.add_argument(
        "-t",
        "--temps-max",
        type=float,
        default=30.0,
        help="temps maximal de résolution par objectif, en secondes (défaut : 30)",
    )
    parser.add_argument(
        "--graine", type=int, default=0, help="graine aléatoire du solveur (défaut : 0)"
    )
    return parser


def _print_stages(result: Result) -> None:
    for stage in result.stages:
        quality = "optimal" if stage.proven else "meilleur trouvé"
        print(f"  - {stage.label} : {stage.value:g} ({quality})")


def _write(args, season, fixtures, stem, warnings=None, rules=None) -> int:
    """Check the schedule against ``rules`` (default: the season), then print and save it."""
    problems = validateur.check(rules or season, fixtures)
    if problems:
        print(
            "Erreur interne : le calendrier trouvé ne passe pas la vérification.", file=sys.stderr
        )
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return INTERNAL_ERROR
    summary = validateur.summarize(season, fixtures)
    directory = args.sortie or args.config.parent
    try:
        md_path, csv_path = export.write(directory, stem, season, fixtures, summary, warnings)
    except export.OverwriteError as exc:
        print(str(exc), file=sys.stderr)
        return OUTPUT_ERROR
    print()
    print(export.markdown(season, fixtures, summary, warnings))
    print(f"Fichiers écrits : {md_path} et {csv_path}")
    return OK


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        season = config.load(args.config)
    except config.ConfigError as exc:
        print(f"Configuration invalide ({args.config}) :", file=sys.stderr)
        for error in exc.errors:
            print(f"  - {error}", file=sys.stderr)
        return INVALID_CONFIG

    options = Options(time_limit=args.temps_max, seed=args.graine)
    print(
        f"{season.name} : {len(season.teams)} équipes, {len(season.dates)} dates. "
        f"Résolution (au plus {args.temps_max:g} s par objectif)…"
    )
    result = solve(season, options)

    if result.found:
        _print_stages(result)
        if result.status != "optimal":
            print("  (augmenter --temps-max peut améliorer le résultat)")
        return _write(args, season, result.fixtures, f"{args.config.stem}-calendrier")

    if result.status == "inconnu":
        print(
            "Aucune solution trouvée dans le temps imparti, sans preuve qu'il n'en existe pas. "
            "Réessayez avec un --temps-max plus grand.",
            file=sys.stderr,
        )
        return NO_ANSWER

    print("Calendrier impossible. Recherche des contraintes en cause…")
    diagnosis = diagnostic.diagnose(season, options)
    print()
    print(diagnostic.report(diagnosis))
    if diagnosis.fallback and diagnosis.fallback.found:
        dropped = diagnosis.options[0]
        code = _write(
            args,
            season,
            diagnosis.fallback.fixtures,
            f"{args.config.stem}-calendrier-provisoire",
            warnings=[f"Ignoré : {s.description}." for s in dropped],
            rules=diagnostic.without(season, dropped),
        )
        if code != OK:
            return code
    return IMPOSSIBLE


if __name__ == "__main__":
    raise SystemExit(main())
