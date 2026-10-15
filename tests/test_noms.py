from planificateur.noms import closest, normalize, unknown_message

TEAMS = ["La Fanfare", "L'Étoile Filante", "Les Rêveur·euse·s", "O'Délire"]


def test_normalize_ignores_case_accents_and_apostrophes():
    assert normalize("L’ETOILE  filante") == normalize("L'Étoile Filante")


def test_normalize_ignores_middle_dots():
    assert normalize("Les Rêveur.euse.s") == normalize("Les Rêveur·euse·s")


def test_closest_finds_typos():
    assert closest("la fanfare", TEAMS) == "La Fanfare"
    assert closest("L’Étoile Filante", TEAMS) == "L'Étoile Filante"
    assert closest("Les Rêveureuses", TEAMS) == "Les Rêveur·euse·s"
    assert closest("ODélire", TEAMS) == "O'Délire"


def test_closest_returns_none_when_nothing_is_close():
    assert closest("Grand Tumulte", TEAMS) is None


def test_message_suggests_or_lists_names():
    assert "Vouliez-vous dire « O'Délire » ?" in unknown_message("Équipe", "O’Délire", TEAMS, "x")
    assert "Noms valides" in unknown_message("Équipe", "Zorro", TEAMS, "x")
