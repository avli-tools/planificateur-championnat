"""Small anonymized seasons for the tests."""

import copy

from planificateur import config
from planificateur.resolution import Options

# Five teams, two matches each, five weekly dates: each team organizes once.
BASE = {
    "saison": "Test",
    "equipes": ["A", "B", "C", "D", "E"],
    "parametres": {
        "matchs_par_equipe": 2,
        "charge_matchs": {"maximum": 2, "jours": 31},
        "charge_engagements": {"maximum": 3, "jours": 7},
    },
    "dates": ["01/09/2025", "08/09/2025", "15/09/2025", "22/09/2025", "29/09/2025"],
}

FAST = Options(time_limit=10, workers=4)


def make_data(params=None, **sections):
    data = copy.deepcopy(BASE)
    data.update(sections)
    data["parametres"].update(params or {})
    return data


def make_season(params=None, **sections) -> config.Season:
    return config.parse(make_data(params, **sections))


def d(text: str):
    """Date from JJ/MM/AAAA."""
    import datetime as dt

    return dt.datetime.strptime(text, "%d/%m/%Y").date()
