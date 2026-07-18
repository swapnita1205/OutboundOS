"""Embedding-based semantic similarity for evaluation scoring.

Token-overlap metrics score paraphrases as total misses: "knowledge scattered
across disconnected tools" vs "teams struggle with fragmented information"
share almost no tokens but describe the same pain point. Comparing against
independent human-authored ground truth (which uses different vocabulary than
any LLM), that weakness dominates the score. This module embeds both sides
with OpenAI embeddings and compares them with cosine similarity so paraphrases
can earn credit.

When no OpenAI key is configured (CI, offline dev), the matcher is disabled
and callers fall back to pure token overlap.
"""

import logging
from math import sqrt

from openai import AsyncOpenAI

from app.utils.settings import Settings

logger = logging.getLogger("outboundos.evaluation.semantic")

EMBEDDING_MODEL = "text-embedding-3-small"


class SemanticMatcher:
    def __init__(self, settings: Settings) -> None:
        api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        self._client: AsyncOpenAI | None = AsyncOpenAI(api_key=api_key) if api_key else None
        self._cache: dict[str, list[float]] = {}

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def similarity_matrix(
        self,
        rows: list[str],
        cols: list[str],
    ) -> list[list[float]] | None:
        """Cosine similarity for every rows x cols pair, or None when unavailable.

        Returning None (instead of raising) lets scoring degrade gracefully to
        token overlap mid-run if the embeddings API has a transient failure.
        """
        if self._client is None or not rows or not cols:
            return None
        unique_texts = list(dict.fromkeys([*rows, *cols]))
        try:
            embeddings = await self._embed(unique_texts)
        except Exception:  # noqa: BLE001
            logger.warning("embedding_failed_falling_back_to_token_overlap", exc_info=True)
            return None
        return [
            [_cosine(embeddings[row], embeddings[col]) for col in cols]
            for row in rows
        ]

    async def _embed(self, texts: list[str]) -> dict[str, list[float]]:
        assert self._client is not None
        missing = [text for text in texts if text not in self._cache]
        if missing:
            response = await self._client.embeddings.create(model=EMBEDDING_MODEL, input=missing)
            for text, item in zip(missing, response.data, strict=True):
                self._cache[text] = item.embedding
        return {text: self._cache[text] for text in texts}


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
