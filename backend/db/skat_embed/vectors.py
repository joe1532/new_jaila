"""Validering og serialisering af 1536-dimensionelle vektorer."""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence

from backend.db.skat_embed.constants import DIMENSIONS
from backend.db.skat_embed.errors import VectorValidationError


def to_float32(values: Sequence[float]) -> list[float]:
    packed = struct.pack("<" + "f" * len(values), *[float(item) for item in values])
    return list(struct.unpack("<" + "f" * len(values), packed))


def validate_embedding(values: Sequence[float], *, dimensions: int = DIMENSIONS) -> list[float]:
    if len(values) != dimensions:
        raise VectorValidationError(f"forventede {dimensions} dimensioner, fik {len(values)}")
    finite = []
    for index, raw in enumerate(values):
        number = float(raw)
        if not math.isfinite(number):
            raise VectorValidationError(f"ikke-finite tal på index {index}")
        finite.append(number)
    casted = to_float32(finite)
    if not any(item != 0.0 for item in casted):
        raise VectorValidationError("nul-vektor")
    if len(casted) != dimensions:
        raise VectorValidationError(f"float32-cast ændrede længden til {len(casted)}")
    return casted


def pgvector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(item)) for item in values) + "]"
