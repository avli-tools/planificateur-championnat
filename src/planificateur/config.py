"""Season configuration: YAML loading and validation.

Validation only checks that the file is well formed (known names, valid dates,
consistent parameters). Contradictions between constraints (e.g. a forced
presence on an unavailable date) are reported by the diagnostic module.
"""

import datetime as dt
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from planificateur.noms import closest, unknown_message

DATE_FORMAT = "%d/%m/%Y"
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

_TOP_LEVEL_KEYS = (
    "saison",
    "equipes",
    "parametres",
    "dates",
    "indisponibilites",
    "presences_imposees",
    "rencontres_interdites",
    "rencontres_imposees",
    "matchs_fixes",
)
_PARAMETER_KEYS = (
    "matchs_par_equipe",
    "matchs_par_date",
    "organisations_par_equipe",
    "charge_matchs",
    "charge_engagements",
)
_LOAD_KEYS = ("maximum", "jours")
_FIXED_MATCH_KEYS = ("date", "equipes", "organisatrice")


class ConfigError(Exception):
    """Invalid configuration; ``errors`` lists every problem found, in French."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class FixedMatch:
    date: dt.date
    teams: tuple[str, str]
    organizer: str | None = None


@dataclass(frozen=True)
class Load:
    """At most ``maximum`` events in any period of ``days`` consecutive days."""

    maximum: int
    days: int


@dataclass(frozen=True)
class Season:
    name: str
    teams: tuple[str, ...]
    dates: tuple[dt.date, ...]
    matches_per_team: int
    matches_per_date: int
    organizations_per_team: int
    match_load: Load
    engagement_load: Load
    unavailable: frozenset[tuple[str, dt.date]] = field(default_factory=frozenset)
    forced: frozenset[tuple[str, dt.date]] = field(default_factory=frozenset)
    forbidden_pairs: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    required_pairs: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    fixed_matches: tuple[FixedMatch, ...] = ()

    def pair(self, a: str, b: str) -> tuple[str, str]:
        """Canonical pair order: the order of declaration in ``teams``."""
        return (a, b) if self.teams.index(a) < self.teams.index(b) else (b, a)

    @property
    def engagements_per_team(self) -> int:
        return self.matches_per_team + self.organizations_per_team

    @property
    def length_days(self) -> int:
        return (self.dates[-1] - self.dates[0]).days


def format_date(date: dt.date) -> str:
    return date.strftime(DATE_FORMAT)


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate keys instead of silently keeping the last one."""


def _construct_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict:
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node)
        if key in seen:
            line = key_node.start_mark.line + 1
            raise ConfigError([f"Clé « {key} » répétée (ligne {line})."])
        seen.add(key)
    return loader.construct_mapping(node)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load(path: str | Path) -> Season:
    """Read and validate a season file. Raises ConfigError."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError([f"Fichier introuvable : {path}"]) from None
    try:
        data = yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ConfigError([f"Fichier YAML illisible ({path}) : {exc}"]) from None
    return parse(data)


def parse(data: Any) -> Season:
    """Validate an already-loaded YAML document. Raises ConfigError."""
    return _Parser(data).parse()


class _Parser:
    def __init__(self, data: Any):
        self.data = data
        self.errors: list[str] = []
        self.teams: list[str] = []
        self.dates: list[dt.date] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def parse(self) -> Season:
        if not isinstance(self.data, Mapping):
            raise ConfigError(
                ["Le fichier doit contenir un dictionnaire (clés « equipes », « dates »…)."]
            )
        self._check_keys(self.data, _TOP_LEVEL_KEYS, "le fichier")
        for required in ("equipes", "parametres", "dates"):
            if required not in self.data:
                self.error(f"Section obligatoire manquante : « {required} ».")

        self.teams = self._parse_teams(self.data.get("equipes"))
        self.dates = self._parse_dates(self.data.get("dates"))
        params = self._parse_parameters(self.data.get("parametres"))
        unavailable = self._parse_by_date(self.data.get("indisponibilites"), "indisponibilites")
        forced = self._parse_by_date(self.data.get("presences_imposees"), "presences_imposees")
        forbidden = self._parse_pairs(
            self.data.get("rencontres_interdites"), "rencontres_interdites"
        )
        required = self._parse_pairs(self.data.get("rencontres_imposees"), "rencontres_imposees")
        fixed = self._parse_fixed(self.data.get("matchs_fixes"), params.get("matchs_par_date"))

        if self.errors:
            raise ConfigError(self.errors)

        name = self.data.get("saison")
        teams = tuple(self.teams)
        season = Season(
            name=str(name) if name is not None else "Saison",
            teams=teams,
            dates=tuple(sorted(self.dates)),
            matches_per_team=params["matchs_par_equipe"],
            matches_per_date=params["matchs_par_date"],
            organizations_per_team=params["organisations_par_equipe"],
            match_load=params["charge_matchs"],
            engagement_load=params["charge_engagements"],
            unavailable=frozenset(unavailable),
            forced=frozenset(forced),
            fixed_matches=tuple(fixed),
        )
        return _with_pairs(season, forbidden, required)

    # -- helpers ---------------------------------------------------------------

    def _check_keys(self, mapping: Mapping, allowed: tuple[str, ...], where: str) -> None:
        for key in mapping:
            if key not in allowed:
                message = f"Clé inconnue « {key} » dans {where}."
                suggestion = closest(str(key), list(allowed))
                if suggestion:
                    message += f" Vouliez-vous dire « {suggestion} » ?"
                else:
                    message += " Clés possibles : " + ", ".join(allowed) + "."
                self.error(message)

    def _team(self, name: Any, where: str) -> str | None:
        if isinstance(name, str) and name in self.teams:
            return name
        if self.teams:
            self.error(unknown_message("Équipe", name, self.teams, where))
        return None

    def _date(self, value: Any, where: str, must_be_listed: bool = True) -> dt.date | None:
        if isinstance(value, dt.date):
            self.error(
                f"Date « {value.isoformat()} » dans {where} : utilisez le format JJ/MM/AAAA "
                f"(par exemple « {format_date(value)} »)."
            )
            return None
        if not isinstance(value, str) or not _DATE_RE.match(value.strip()):
            self.error(f"Date mal formée « {value} » dans {where} : format attendu JJ/MM/AAAA.")
            return None
        try:
            date = dt.datetime.strptime(value.strip(), DATE_FORMAT).date()
        except ValueError:
            self.error(f"Date inexistante « {value} » dans {where}.")
            return None
        if must_be_listed and self.dates and date not in self.dates:
            self.error(f"La date « {value} » ({where}) ne fait pas partie des dates de la saison.")
            return None
        return date

    def _list(self, value: Any, where: str) -> list:
        if value is None:
            return []
        if not isinstance(value, list):
            self.error(f"« {where} » doit être une liste.")
            return []
        return value

    # -- sections --------------------------------------------------------------

    def _parse_teams(self, value: Any) -> list[str]:
        teams: list[str] = []
        for item in self._list(value, "equipes"):
            if not isinstance(item, str) or not item.strip():
                self.error(f"Nom d'équipe invalide dans « equipes » : « {item} ».")
            elif item in teams:
                self.error(f"Équipe « {item} » déclarée deux fois dans « equipes ».")
            else:
                teams.append(item)
        return teams

    def _parse_dates(self, value: Any) -> list[dt.date]:
        dates: list[dt.date] = []
        for item in self._list(value, "dates"):
            date = self._date(item, "« dates »", must_be_listed=False)
            if date is None:
                continue
            if date in dates:
                self.error(f"Date « {item} » présente deux fois dans « dates ».")
            else:
                dates.append(date)
        return dates

    def _parse_load(self, value: Any, key: str) -> Load | None:
        where = f"« parametres › {key} »"
        if not isinstance(value, Mapping):
            self.error(f"{where} doit contenir « maximum » et « jours ».")
            return None
        self._check_keys(value, _LOAD_KEYS, where)
        numbers = []
        for sub in _LOAD_KEYS:
            raw = value.get(sub)
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
                self.error(
                    f"« parametres › {key} › {sub} » doit être un entier ≥ 1 (reçu « {raw} »)."
                )
                return None
            numbers.append(raw)
        return Load(*numbers)

    def _parse_parameters(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            self.error("« parametres » doit être un dictionnaire.")
            return {}
        self._check_keys(value, _PARAMETER_KEYS, "« parametres »")

        params: dict[str, Any] = {}
        defaults = {"matchs_par_date": 1}
        for key in _PARAMETER_KEYS:
            raw = value.get(key, defaults.get(key))
            if raw is None:
                if key != "organisations_par_equipe":
                    self.error(f"Paramètre obligatoire manquant : « parametres › {key} ».")
                continue
            if key.startswith("charge_"):
                load = self._parse_load(raw, key)
                if load is not None:
                    params[key] = load
                continue
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                self.error(f"« parametres › {key} » doit être un entier positif (reçu « {raw} »).")
                continue
            params[key] = raw

        n_teams, n_dates = len(self.teams), len(self.dates)
        if not (
            n_teams and n_dates and "matchs_par_equipe" in params and "matchs_par_date" in params
        ):
            return params

        per_team, per_date = params["matchs_par_equipe"], params["matchs_par_date"]
        if per_date < 1:
            self.error("« parametres › matchs_par_date » doit valoir au moins 1.")
        if n_teams * per_team != 2 * per_date * n_dates:
            self.error(
                f"Paramètres incohérents : {n_teams} équipes × {per_team} matchs = "
                f"{n_teams * per_team} places, mais {n_dates} dates × {per_date} match(s) × 2 "
                f"= {2 * per_date * n_dates} places."
            )
        if n_teams < 2 * per_date + 1:
            self.error(
                f"Il faut au moins {2 * per_date + 1} équipes pour {per_date} match(s) "
                "et une organisatrice par date."
            )
        organizations = params.get("organisations_par_equipe")
        if organizations is None:
            if n_dates % n_teams:
                self.error(
                    f"{n_dates} dates ne se répartissent pas équitablement entre {n_teams} équipes "
                    "pour l'organisation."
                )
            else:
                params["organisations_par_equipe"] = n_dates // n_teams
        elif organizations * n_teams != n_dates:
            self.error(
                f"Paramètres incohérents : {n_teams} équipes × {organizations} organisations "
                f"= {organizations * n_teams}, mais il y a {n_dates} dates à organiser."
            )
        return params

    def _parse_by_date(self, value: Any, section: str) -> set[tuple[str, dt.date]]:
        result: set[tuple[str, dt.date]] = set()
        if value is None:
            return result
        if not isinstance(value, Mapping):
            self.error(f"« {section} » doit associer des dates à des listes d'équipes.")
            return result
        for raw_date, names in value.items():
            where = f"« {section} › {raw_date} »"
            date = self._date(raw_date, where)
            if isinstance(names, str):
                names = [names]
            for name in self._list(names, f"{section} › {raw_date}"):
                team = self._team(name, where)
                if team is not None and date is not None:
                    result.add((team, date))
        return result

    def _parse_teams_pair(self, value: Any, where: str) -> tuple[str, str] | None:
        if not isinstance(value, list) or len(value) != 2:
            self.error(
                f"{where} : il faut exactement deux équipes, par exemple [Équipe A, Équipe B]."
            )
            return None
        a, b = self._team(value[0], where), self._team(value[1], where)
        if a is None or b is None:
            return None
        if a == b:
            self.error(f"{where} : une équipe ne peut pas s'affronter elle-même (« {a} »).")
            return None
        return a, b

    def _parse_pairs(self, value: Any, section: str) -> list[tuple[str, str]]:
        pairs = []
        for i, item in enumerate(self._list(value, section), start=1):
            pair = self._parse_teams_pair(item, f"« {section} » (n° {i})")
            if pair is not None:
                pairs.append(pair)
        return pairs

    def _parse_fixed(self, value: Any, matches_per_date: int | None) -> list[FixedMatch]:
        fixed: list[FixedMatch] = []
        for i, item in enumerate(self._list(value, "matchs_fixes"), start=1):
            where = f"« matchs_fixes » (n° {i})"
            if not isinstance(item, Mapping):
                self.error(
                    f"{where} : attendu « date », « equipes » et éventuellement « organisatrice »."
                )
                continue
            self._check_keys(item, _FIXED_MATCH_KEYS, where)
            if "date" not in item or "equipes" not in item:
                self.error(f"{where} : « date » et « equipes » sont obligatoires.")
                continue
            date = self._date(item["date"], where)
            pair = self._parse_teams_pair(item["equipes"], where)
            organizer = None
            if item.get("organisatrice") is not None:
                organizer = self._team(item["organisatrice"], where)
                if pair is not None and organizer in pair:
                    self.error(
                        f"{where} : l'organisatrice « {organizer} » ne peut pas jouer ce match."
                    )
            if date is not None and pair is not None:
                fixed.append(FixedMatch(date, pair, organizer))

        for i, match in enumerate(fixed):
            for other in fixed[i + 1 :]:
                if set(match.teams) == set(other.teams):
                    self.error(
                        f"Le match {match.teams[0]} – {match.teams[1]} est fixé deux fois "
                        f"({format_date(match.date)} et {format_date(other.date)})."
                    )
                elif match.date == other.date and (
                    set(match.teams) & set(other.teams) or matches_per_date == 1
                ):
                    self.error(f"Deux matchs fixés incompatibles le {format_date(match.date)}.")
                elif (
                    match.date == other.date
                    and match.organizer
                    and other.organizer
                    and match.organizer != other.organizer
                ):
                    self.error(
                        f"Deux organisatrices différentes fixées le {format_date(match.date)}."
                    )
        return fixed


def _with_pairs(
    season: Season, forbidden: list[tuple[str, str]], required: list[tuple[str, str]]
) -> Season:
    """Store forbidden pairs, required pairs and fixed-match teams in canonical order."""
    fixed = tuple(
        FixedMatch(m.date, season.pair(*m.teams), m.organizer) for m in season.fixed_matches
    )
    return replace(
        season,
        forbidden_pairs=frozenset(season.pair(a, b) for a, b in forbidden),
        required_pairs=frozenset(season.pair(a, b) for a, b in required),
        fixed_matches=fixed,
    )
