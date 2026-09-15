"""OpenAI embeddings.create med batching, indexrækkefølge og retry. Ingen tekst i logs."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from backend.db.skat_embed.constants import (
    BACKOFF_BASE_SECONDS,
    BACKOFF_MAX_SECONDS,
    DEFAULT_BATCH_INPUTS,
    DEFAULT_BATCH_TOKENS,
    DIMENSIONS,
    ENCODING_FORMAT,
    MAX_BATCH_INPUTS,
    MAX_BATCH_TOKENS,
    MAX_RETRIES,
    MODEL_NAME,
    RETRYABLE_STATUS,
)
from backend.db.skat_embed.errors import SkatEmbedError, VectorValidationError
from backend.db.skat_embed.keys import openai_api_key, redact_secrets
from backend.db.skat_embed.vectors import validate_embedding


class EmbeddingsAPI(Protocol):
    def embeddings_create(
        self,
        *,
        model: str,
        dimensions: int,
        input: list[str],
        encoding_format: str,
    ) -> "EmbedResponse":
        ...


@dataclass(frozen=True)
class EmbedResponse:
    embeddings: list[list[float]]
    model: str
    prompt_tokens: int
    total_tokens: int
    request_id: str | None
    http_status: int
    attempts: int = 1


@dataclass(frozen=True)
class BatchItem:
    item_id: str
    text: str
    token_count: int


def split_batches(
    items: list[BatchItem],
    *,
    max_inputs: int = DEFAULT_BATCH_INPUTS,
    max_tokens: int = DEFAULT_BATCH_TOKENS,
) -> list[list[BatchItem]]:
    input_cap = min(max(1, max_inputs), MAX_BATCH_INPUTS)
    token_cap = min(max(1, max_tokens), MAX_BATCH_TOKENS)
    batches: list[list[BatchItem]] = []
    current: list[BatchItem] = []
    tokens = 0
    for item in items:
        item_tokens = max(1, int(item.token_count))
        overflows = current and (
            len(current) >= input_cap or tokens + item_tokens > token_cap
        )
        if overflows:
            batches.append(current)
            current = []
            tokens = 0
        current.append(item)
        tokens += item_tokens
    if current:
        batches.append(current)
    return batches


def order_embeddings(raw_items: list[Any], input_count: int) -> list[list[float]]:
    by_index: dict[int, list[float]] = {}
    for item in raw_items:
        index = int(getattr(item, "index", item["index"] if isinstance(item, dict) else -1))
        vector = getattr(item, "embedding", None)
        if vector is None and isinstance(item, dict):
            vector = item["embedding"]
        if index in by_index:
            raise VectorValidationError(f"duplikeret embedding-index {index}")
        by_index[index] = list(vector)
    expected = set(range(input_count))
    if set(by_index) != expected:
        raise VectorValidationError(
            f"embedding-index matcher ikke inputrækkefølgen: fik {sorted(by_index)}"
        )
    return [by_index[index] for index in range(input_count)]


def backoff_seconds(attempt: int, *, rng: random.Random | None = None) -> float:
    delay = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
    jitter = (rng or random).uniform(0, 1)
    return delay + jitter


def is_retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if status in RETRYABLE_STATUS:
        return True
    name = type(exc).__name__
    if name in {"RateLimitError", "APIConnectionError", "APITimeoutError", "InternalServerError"}:
        return True
    return False


class OpenAIEmbeddingsClient:
    def __init__(self, inner: Any | None = None) -> None:
        self._inner = inner

    def _client(self) -> Any:
        if self._inner is not None:
            return self._inner
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise SkatEmbedError("openai-pakken mangler") from exc
        return OpenAI(api_key=openai_api_key())

    def embeddings_create(
        self,
        *,
        model: str,
        dimensions: int,
        input: list[str],
        encoding_format: str,
    ) -> EmbedResponse:
        client = self._client()
        response = client.embeddings.create(
            model=model,
            dimensions=dimensions,
            input=input,
            encoding_format=encoding_format,
        )
        raw_items = list(response.data)
        if len(raw_items) != len(input):
            raise VectorValidationError(
                f"API returnerede {len(raw_items)} embeddings til {len(input)} inputs"
            )
        ordered = order_embeddings(raw_items, len(input))
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
        request_id = getattr(response, "_request_id", None) or getattr(response, "id", None)
        model_name = str(getattr(response, "model", model) or model)
        return EmbedResponse(
            embeddings=ordered,
            model=model_name,
            prompt_tokens=prompt_tokens,
            total_tokens=total_tokens,
            request_id=str(request_id) if request_id else None,
            http_status=200,
            attempts=1,
        )


def embed_texts(
    texts: list[str],
    *,
    client: EmbeddingsAPI | None = None,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> EmbedResponse:
    api = client or OpenAIEmbeddingsClient()
    last_error: BaseException | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = api.embeddings_create(
                model=MODEL_NAME,
                dimensions=DIMENSIONS,
                input=texts,
                encoding_format=ENCODING_FORMAT,
            )
            validated = [validate_embedding(vector) for vector in result.embeddings]
            if len(validated) != len(texts):
                raise VectorValidationError("valideret antal matcher ikke input")
            return EmbedResponse(
                embeddings=validated,
                model=result.model,
                prompt_tokens=result.prompt_tokens,
                total_tokens=result.total_tokens,
                request_id=result.request_id,
                http_status=result.http_status,
                attempts=attempt,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= MAX_RETRIES or not is_retryable(exc):
                raise SkatEmbedError(redact_secrets(str(exc))) from exc
            sleep(backoff_seconds(attempt, rng=rng))
    raise SkatEmbedError(redact_secrets(str(last_error)))
