"""Fejltyper for retrieval. Ingen hemmeligheder i beskeder."""


EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_DATABASE = 4
EXIT_INTEGRITY = 5


class SkatRetrievalError(Exception):
    """Basisklasse for retrievalfejl."""

    exit_code = EXIT_DATABASE
    error_code = "retrieval_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class CliArgumentError(SkatRetrievalError):
    exit_code = EXIT_USAGE
    error_code = "invalid_argument"


class IdentifierNotFoundError(SkatRetrievalError):
    """SKM-nummer eller OID findes ikke i legal_documents."""

    exit_code = EXIT_NOT_FOUND
    error_code = "identifier_not_found"


class DatabaseUnavailableError(SkatRetrievalError):
    exit_code = EXIT_DATABASE
    error_code = "database_error"


class QueryEmbeddingUnavailableError(DatabaseUnavailableError):
    """Ingen gyldig query-embedding til vector/exact."""

    error_code = "query_embedding_unavailable"

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message, details={"reason": reason})
        self.reason = reason


class RetrievalIntegrityError(SkatRetrievalError):
    exit_code = EXIT_INTEGRITY
    error_code = "integrity_error"
