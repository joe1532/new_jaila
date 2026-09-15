"""Fejltyper. Ingen API-nøgle og ingen dokumenttekst i beskeder."""


class SkatEmbedError(Exception):
    """Basisklasse for embeddingfejl."""


class MissingApiKeyError(SkatEmbedError):
    """OPENAI_API_KEY mangler."""


class IntegrityError(SkatEmbedError):
    """Eksisterende embedding med afvigende embedding_text_sha256."""


class VectorValidationError(SkatEmbedError):
    """Vektoren har forkert længde, ikke-finite tal eller er nul."""


class FullCorpusNotApprovedError(SkatEmbedError):
    """Fuld korpus-embedding kræver særskilt godkendelse."""
