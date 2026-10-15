"""Explain why no schedule exists, and what to drop to get one.

Three levels, from the most precise to the most general:

1. quick checks that need no solver (a date without enough available teams…);
2. relaxation: local constraints (unavailability, forced presence, forbidden pair,
   fixed match) may be dropped, and the solver drops as few as possible. Other
   sets of the same size are then searched, to offer alternatives;
3. if nothing local helps, the season parameters themselves are too strict:
   the load limits are loosened one step at a time.
"""

from dataclasses import dataclass, field, replace

from ortools.sat.python import cp_model

from planificateur import modele
from planificateur.config import Load, Season, format_date
from planificateur.resolution import Options, Result, is_feasible, make_solver, solve


@dataclass
class Diagnosis:
    checks: list[str] = field(default_factory=list)
    # Each option is a minimal list of local constraints whose removal makes the season feasible.
    options: list[list[modele.SoftConstraint]] = field(default_factory=list)
    structural: list[str] = field(default_factory=list)
    fallback: Result | None = None  # best schedule once the first option is applied


def quick_checks(season: Season) -> list[str]:
    """Contradictions that are certain and can be found without the solver."""
    problems = []
    unavailable = season.unavailable
    per_date_teams = 2 * season.matches_per_date + 1

    def available(team, date):
        return (team, date) not in unavailable

    for date in season.dates:
        free = [t for t in season.teams if available(t, date)]
        if len(free) < per_date_teams:
            problems.append(
                f"Le {format_date(date)}, seules {len(free)} équipes sont disponibles ; "
                f"il en faut {per_date_teams} (deux par match et une organisatrice)."
            )
        forced = [t for t, d in season.forced if d == date]
        if len(forced) > 2 * season.matches_per_date:
            problems.append(
                f"Le {format_date(date)}, {len(forced)} équipes doivent jouer, "
                f"mais il n'y a que {2 * season.matches_per_date} places."
            )

    for team in season.teams:
        free = [d for d in season.dates if available(team, d)]
        if len(free) < season.engagements_per_team:
            problems.append(
                f"{team} n'est disponible qu'à {len(free)} dates, mais a "
                f"{season.engagements_per_team} engagements (matchs et organisation)."
            )
        forced = sorted(d for t, d in season.forced if t == team)
        if len(forced) > season.matches_per_team:
            problems.append(
                f"{team} doit jouer à {len(forced)} dates, plus que ses "
                f"{season.matches_per_team} matchs."
            )
        for date in forced:
            if not available(team, date):
                problems.append(
                    f"{team} doit jouer le {format_date(date)}, mais y est indisponible."
                )

    for fixed in season.fixed_matches:
        when = format_date(fixed.date)
        a, b = fixed.teams
        for team in (*fixed.teams, fixed.organizer):
            if team and not available(team, fixed.date):
                problems.append(f"Match fixé le {when} : {team} est indisponible ce jour-là.")
        if (a, b) in season.forbidden_pairs:
            problems.append(f"Le match fixé {a} – {b} ({when}) est une rencontre interdite.")
        for team, date in season.forced:
            if date == fixed.date and season.matches_per_date == 1 and team not in fixed.teams:
                problems.append(
                    f"{team} doit jouer le {when}, mais le match fixé ce jour-là est {a} – {b}."
                )

    problems += _window_checks(
        season, season.engagement_load, 2 * season.matches_per_date + 1, "engagements"
    )
    problems += _window_checks(season, season.match_load, 2 * season.matches_per_date, "matchs")
    return problems


def _window_checks(season: Season, load: Load, places_per_date: int, what: str) -> list[str]:
    """Dates packed in fewer than ``load.days`` days need more places than the teams can give."""
    problems, reported = [], []
    dates = season.dates
    for i, start in enumerate(dates):
        window = [d for d in dates[i:] if (d - start).days < load.days]
        if len(window) < 2 or any(set(window) <= set(r) for r in reported):
            continue
        needed = places_per_date * len(window)
        capacity = sum(
            min(load.maximum, sum((team, d) not in season.unavailable for d in window))
            for team in season.teams
        )
        if needed > capacity:
            reported.append(window)
            problems.append(
                f"Les {len(window)} dates du {format_date(window[0])} au {format_date(window[-1])} "
                f"(moins de {load.days} jours) demandent {needed} {what}, mais les équipes ne peuvent "
                f"en assurer que {capacity} (au plus {load.maximum} chacune sur {load.days} jours, "
                "compte tenu des indisponibilités)."
            )
    return problems


def without(season: Season, dropped: list[modele.SoftConstraint]) -> Season:
    """The season without the given local constraints."""
    keys = {s.key for s in dropped}
    return replace(
        season,
        unavailable=frozenset(x for x in season.unavailable if ("indisponibilite", x) not in keys),
        forced=frozenset(x for x in season.forced if ("presence", x) not in keys),
        forbidden_pairs=frozenset(
            x for x in season.forbidden_pairs if ("rencontre_interdite", x) not in keys
        ),
        fixed_matches=tuple(x for x in season.fixed_matches if ("match_fixe", x) not in keys),
    )


def minimal_relaxations(
    season: Season, options: Options, max_options: int = 3
) -> list[list[modele.SoftConstraint]]:
    """Smallest sets of local constraints to drop, best first ([] if dropping all is not enough)."""
    sm = modele.build(season, relax_local=True)
    if not sm.soft:
        return []
    dropped_count = sum(1 - s.kept for s in sm.soft)
    sm.model.minimize(dropped_count)
    solver = make_solver(options)
    status = solver.solve(sm.model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return []
    best = round(solver.objective_value)
    sm.model.clear_objective()
    sm.model.add(dropped_count == best)

    results = []
    while True:
        dropped = [s for s in sm.soft if not solver.value(s.kept)]
        results.append(dropped)
        if len(results) >= max_options:
            break
        # Look for another set of the same size: keep at least one of these constraints.
        sm.model.add_bool_or([s.kept for s in dropped])
        solver = make_solver(options)
        if solver.solve(sm.model) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
    return results


def _structural(season: Season, options: Options) -> list[str]:
    """Which loosened load limit would make the season feasible (local constraints ignored)."""
    bare = without(season, modele.build(season, relax_local=True).soft)
    findings = []
    for attribute, label in (
        ("engagement_load", "charge_engagements"),
        ("match_load", "charge_matchs"),
    ):
        load: Load = getattr(season, attribute)
        for extra in (1, 2, 3):
            looser = replace(bare, **{attribute: Load(load.maximum + extra, load.days)})
            if is_feasible(looser, options):
                findings.append(
                    f"Possible avec « {label} › maximum » = {load.maximum + extra} "
                    f"au lieu de {load.maximum} (sur {load.days} jours)."
                )
                break
    return findings


def diagnose(season: Season, options: Options | None = None) -> Diagnosis:
    options = options or Options()
    diagnosis = Diagnosis(checks=quick_checks(season))
    diagnosis.options = minimal_relaxations(season, options)
    if diagnosis.options:
        diagnosis.fallback = solve(without(season, diagnosis.options[0]), options)
    else:
        diagnosis.structural = _structural(season, options)
    return diagnosis


def report(diagnosis: Diagnosis) -> str:
    lines = ["Aucun calendrier ne respecte toutes les contraintes.", ""]
    if diagnosis.checks:
        lines.append("Problèmes détectés :")
        lines += [f"  - {c}" for c in diagnosis.checks]
        lines.append("")
    if diagnosis.options:
        size = len(diagnosis.options[0])
        noun = "contrainte" if size == 1 else "contraintes"
        lines.append(
            f"Il suffit d'ignorer {size} {noun}. "
            + ("Une possibilité :" if len(diagnosis.options) == 1 else "Possibilités :")
        )
        for i, option in enumerate(diagnosis.options, start=1):
            lines.append(f"  {i}. " + " ; ".join(s.description for s in option))
        lines.append("")
        if diagnosis.fallback and diagnosis.fallback.found:
            lines.append("Un calendrier provisoire est proposé avec la possibilité 1.")
    else:
        lines.append(
            "Même en ignorant toutes les indisponibilités, présences imposées, rencontres "
            "interdites et matchs fixés, aucun calendrier n'existe : les dates ou les paramètres "
            "de la saison sont trop contraignants."
        )
        lines += [f"  - {s}" for s in diagnosis.structural]
    return "\n".join(lines)
