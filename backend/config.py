import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"

VECTOR_STORE_IDS = [
    "vs_67d1e99c789c8191bd776ac5437cbc08",
    "vs_69ab3cf9971c8191be5aaf4eb04d69f0",
    "vs_69ab3fb014748191a642f8059e6d81c7",
    "vs_69ab489f8c4c8191a171e90acb5147ad",
    "vs_69ab5288601c8191b34fa40268dd8537",
]

PRIMARY_MODEL = "gpt-5.4"
FALLBACK_MODEL = "gpt-5.2"
MAX_NUM_RESULTS = 10
STRICT_SOURCING = os.getenv("STRICT_SOURCING", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

ANSWER_INSTRUCTIONS = (
    "Du er en juridisk assistent. Svar på dansk. "
    "Brug kun oplysninger, der kan underbygges af file_search-kilderne. "
    "Skriv ikke 'Karnov-noter' som kildebetegnelse; brug i stedet "
    "'Note til relevant lovbestemmelse' eller et konkret lovnavn. "
    "Når du henviser til en note, skal den skrives med notenummer i parentes, "
    "fx 'Note (454) til ligningslovens § 9 C ...'. "
    "Afslut ALTID svaret med en sektion med overskriften "
    "'Anvendte kilder/love' efterfulgt af korte punktlinjer med de centrale "
    "kilder/love, du faktisk har anvendt i analysen."
)


def get_allowed_origins() -> list[str]:
    raw = os.getenv("FRONTEND_ORIGINS", "https://skat-chat.dk,http://localhost:3000")
    origins = [x.strip() for x in raw.split(",") if x.strip()]
    return origins or ["*"]
