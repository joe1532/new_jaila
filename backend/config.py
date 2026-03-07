import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"

VECTOR_STORE_IDS = [
    "vs_67d1e99c789c8191bd776ac5437cbc08",
    "vs_69ab3cf9971c8191be5aaf4eb04d69f0",
]

PRIMARY_MODEL = "gpt-5.4"
FALLBACK_MODEL = "gpt-5.2"
MAX_NUM_RESULTS = 10

ANSWER_INSTRUCTIONS = (
    "Du er en juridisk assistent. Svar på dansk. "
    "Brug kun oplysninger, der kan underbygges af file_search-kilderne. "
    "Afslut ALTID svaret med en sektion med overskriften "
    "'Anvendte kilder/love' efterfulgt af korte punktlinjer med de centrale "
    "kilder/love, du faktisk har anvendt i analysen."
)


def get_allowed_origins() -> list[str]:
    raw = os.getenv("FRONTEND_ORIGINS", "https://skat-chat.dk,http://localhost:3000")
    origins = [x.strip() for x in raw.split(",") if x.strip()]
    return origins or ["*"]
