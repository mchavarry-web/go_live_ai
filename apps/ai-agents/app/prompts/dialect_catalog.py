"""Dialect catalog for language style adaptation.

Maps ISO 3166-1 alpha-2 country codes to linguistic profiles including
pronoun usage, conjugation style, slang by formality level, filler words,
and expressions to avoid (from other dialects).

The catalog is consumed by ``_build_language_style_section`` in
``avatar_prompts.py`` to inject dialect-aware instructions into the
system prompt.
"""

from typing import TypedDict


class DialectProfile(TypedDict):
    """Linguistic profile for a specific country/dialect."""

    name: str
    pronoun: str
    conjugation_hint: str
    slang_casual: list[str]
    slang_moderate: list[str]
    fillers: list[str]
    avoid: list[str]


DIALECT_CATALOG: dict[str, DialectProfile] = {
    "ar": {
        "name": "rioplatense",
        "pronoun": "vos",
        "conjugation_hint": "voseo (tenés, sos, querés, dale)",
        "slang_casual": [
            "che", "boludo/a", "dale", "re", "posta", "flashear",
            "chabón", "morfar", "afanar", "garpar", "al toque",
        ],
        "slang_moderate": [
            "dale", "posta", "tipo", "onda", "nah", "re", "buenísimo",
        ],
        "fillers": ["o sea", "bah", "ponele", "digamos", "nada"],
        "avoid": ["wey", "parce", "pe", "po", "tío", "vale"],
    },
    "mx": {
        "name": "mexicano",
        "pronoun": "tú",
        "conjugation_hint": "tuteo (tienes, eres, quieres, ándale)",
        "slang_casual": [
            "wey/güey", "neta", "chido", "naco", "nomas", "mande",
            "chamba", "lana", "cuate", "padre", "órale",
        ],
        "slang_moderate": [
            "órale", "chido", "neta", "sale", "va", "qué onda", "padre",
        ],
        "fillers": ["o sea", "tipo", "la neta", "onda", "pues"],
        "avoid": ["boludo", "che", "parce", "pe", "tío", "vale"],
    },
    "pe": {
        "name": "peruano",
        "pronoun": "tú",
        "conjugation_hint": "tuteo (tienes, eres, quieres)",
        "slang_casual": [
            "pe", "causa", "manyas", "pata", "jato", "asu mare",
            "chamba", "pechito", "floro", "jalar", "pituco",
        ],
        "slang_moderate": [
            "pe", "chévere", "bacán", "causa", "ya pe", "pata",
        ],
        "fillers": ["pe", "pues", "o sea", "ya", "ah ya"],
        "avoid": ["boludo", "che", "wey", "parce", "tío", "vale"],
    },
    "co": {
        "name": "colombiano",
        "pronoun": "tú/usted",
        "conjugation_hint": "tuteo o ustedeo según región (tienes/tiene, eres/es)",
        "slang_casual": [
            "parce", "marica", "bacano", "chimba", "parcero",
            "berraco", "gonorrea", "parchar", "rumba", "tinto",
        ],
        "slang_moderate": [
            "parce", "bacano", "chévere", "listo", "qué más", "hermano",
        ],
        "fillers": ["pues", "o sea", "ve", "ey"],
        "avoid": ["boludo", "che", "wey", "pe", "tío", "vale"],
    },
    "cl": {
        "name": "chileno",
        "pronoun": "tú/vos",
        "conjugation_hint": "tuteo o voseo chileno (tenís, erís, querís, cachai)",
        "slang_casual": [
            "po", "weón/huevón", "cachai", "fome", "bacán", "cuático",
            "al tiro", "pega", "pololo/a", "carrete", "la raja",
        ],
        "slang_moderate": [
            "po", "cachai", "bacán", "dale", "ya po", "la raja",
        ],
        "fillers": ["po", "o sea", "cachai", "como que"],
        "avoid": ["boludo", "che", "wey", "parce", "pe", "tío", "vale"],
    },
    "es": {
        "name": "español peninsular",
        "pronoun": "tú/vosotros",
        "conjugation_hint": "tuteo peninsular (tienes, eres, queréis, vale)",
        "slang_casual": [
            "tío/a", "vale", "mola", "flipar", "currar", "molar",
            "guay", "quedada", "pasta", "chaval", "coño",
        ],
        "slang_moderate": [
            "tío/a", "vale", "mola", "guay", "genial", "chaval",
        ],
        "fillers": ["o sea", "bueno", "vamos", "en plan"],
        "avoid": ["boludo", "che", "wey", "parce", "pe"],
    },
    "uy": {
        "name": "uruguayo",
        "pronoun": "vos/tú",
        "conjugation_hint": "voseo (tenés, sos, querés) similar al rioplatense",
        "slang_casual": [
            "bo", "ta", "botija", "champión", "bárbaro", "divino",
        ],
        "slang_moderate": [
            "bo", "ta", "bárbaro", "divino", "dale",
        ],
        "fillers": ["ta", "o sea", "ponele", "bah"],
        "avoid": ["wey", "parce", "pe", "po", "tío"],
    },
    "ec": {
        "name": "ecuatoriano",
        "pronoun": "tú/vos",
        "conjugation_hint": "tuteo o voseo según región",
        "slang_casual": [
            "chuta", "ñaño/a", "bacán", "chévere", "achachay",
            "verás", "de ley", "man",
        ],
        "slang_moderate": [
            "chévere", "bacán", "de ley", "ñaño/a", "verás",
        ],
        "fillers": ["pues", "o sea", "verás", "ya"],
        "avoid": ["boludo", "che", "wey", "parce", "pe", "po"],
    },
    "ve": {
        "name": "venezolano",
        "pronoun": "tú",
        "conjugation_hint": "tuteo (tienes, eres, quieres)",
        "slang_casual": [
            "chamo/a", "pana", "marico/a", "vaina", "ladilla",
            "arrechera", "burda", "fino", "chimbo",
        ],
        "slang_moderate": [
            "chamo/a", "pana", "fino", "chévere", "burda", "vaina",
        ],
        "fillers": ["o sea", "mira", "vale", "verga"],
        "avoid": ["boludo", "che", "wey", "parce", "pe", "po", "tío"],
    },
    "us": {
        "name": "english US casual",
        "pronoun": "you",
        "conjugation_hint": "standard American English",
        "slang_casual": [
            "dude", "bro", "ngl", "tbh", "lowkey", "highkey", "sus",
            "goated", "bussin", "bet", "no cap", "slay", "vibe",
        ],
        "slang_moderate": [
            "honestly", "tbh", "like", "kinda", "pretty much", "dude",
        ],
        "fillers": ["like", "I mean", "you know", "honestly", "basically"],
        "avoid": ["mate", "bloke", "innit", "cheers"],
    },
    "gb": {
        "name": "english UK",
        "pronoun": "you",
        "conjugation_hint": "standard British English",
        "slang_casual": [
            "mate", "bloke", "innit", "cheers", "rubbish", "bloody",
            "knackered", "cheeky", "brilliant", "gutted",
        ],
        "slang_moderate": [
            "mate", "cheers", "brilliant", "lovely", "proper",
        ],
        "fillers": ["right", "well", "I mean", "sort of", "basically"],
        "avoid": ["dude", "bro", "ngl", "tbh", "lowkey"],
    },
}


def get_dialect(country_code: str | None) -> DialectProfile | None:
    """Look up a dialect profile by ISO country code.

    Args:
        country_code: Two-letter ISO 3166-1 code (case-insensitive), or None.

    Returns:
        The DialectProfile for the country, or None if not found.
    """
    if not country_code:
        return None
    return DIALECT_CATALOG.get(country_code.lower().strip())
