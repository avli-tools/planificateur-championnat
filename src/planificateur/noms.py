"""Team-name matching: exact names are required, close ones are suggested."""

import difflib
import unicodedata

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'", "ʼ": "'"})


def normalize(name: str) -> str:
    """Loose form of a name: no accents, case, apostrophe variants, punctuation or extra spaces."""
    text = unicodedata.normalize("NFKD", name.translate(_APOSTROPHES))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = "".join(c if c.isalnum() or c == "'" else " " for c in text.casefold())
    return " ".join(text.split())


def closest(name: str, candidates: list[str]) -> str | None:
    """Return the candidate most likely meant by ``name``, or None."""
    target = normalize(name)
    by_normalized = {normalize(c): c for c in candidates}
    if target in by_normalized:
        return by_normalized[target]
    match = difflib.get_close_matches(target, list(by_normalized), n=1, cutoff=0.6)
    return by_normalized[match[0]] if match else None


def unknown_message(kind: str, name: object, candidates: list[str], where: str) -> str:
    """French error message for an unknown name, with a suggestion when one is close."""
    message = f"{kind} inconnue « {name} » dans {where}."
    suggestion = closest(str(name), candidates)
    if suggestion is not None:
        message += f" Vouliez-vous dire « {suggestion} » ?"
    else:
        message += " Noms valides : " + ", ".join(f"« {c} »" for c in candidates) + "."
    return message
