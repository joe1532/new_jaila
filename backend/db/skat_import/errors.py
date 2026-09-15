"""Fejltyper. Ingen databasehemmeligheder i beskeder."""


class SkatImportError(Exception):
    """Basisklasse for importfejl."""


class PreflightError(SkatImportError):
    """Korpus validerer ikke. Ingen databaseændring er sket."""


class HashIntegrityError(SkatImportError):
    """Eksisterende ID med afvigende hash eller identitetskonflikt."""


class MissingResolvedTargetError(SkatImportError):
    """resolved reference peger på et target_document_id, der ikke findes i korpusset."""


class VerifyError(SkatImportError):
    """Databaseindhold matcher ikke de forventede tællinger eller hashes."""
