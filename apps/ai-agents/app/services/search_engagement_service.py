"""Two-turn search-engagement orchestration (Phase 15).

Stores last-turn search context in an in-process LRU keyed by
``(user_id, conversation_id)`` with a 5-minute TTL. Lose-on-restart is
fine — this is a heuristic for opportunistic preference capture, not an
authoritative store. On the *next* turn we read the cached search,
classify engagement, and persist a preference insight when the user
actually engaged.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import logging
import time
from dataclasses import dataclass

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.search_engagement_chain import SearchEngagementChain
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300  # 5 minutes
_CACHE_MAX_ENTRIES = 1000


@dataclass(frozen=True)
class _CacheKey:
    user_id: str
    conversation_id: str


@dataclass
class _SearchContext:
    """Cached snapshot of a prior turn's web_search invocation.

    Re-exported (without the leading underscore) as ``SearchContext`` for
    callers that need to pass it around between request entry and the
    post-turn classification.
    """

    query: str
    summary: str
    cached_at: float


# Public alias for type hints in callers.
SearchContext = _SearchContext


class _SearchContextCache:
    """Tiny TTL cache shared across requests.

    Single instance per process. Bounded by ``_CACHE_MAX_ENTRIES`` so a
    runaway agent can't pile up entries forever; eviction is "drop oldest
    when over cap" rather than full LRU because the cap rarely matters.
    """

    def __init__(self) -> None:
        self._store: dict[_CacheKey, _SearchContext] = {}
        self._lock = asyncio.Lock()

    async def put(self, key: _CacheKey, context: _SearchContext) -> None:
        async with self._lock:
            self._store[key] = context
            if len(self._store) > _CACHE_MAX_ENTRIES:
                # Drop oldest by cached_at — cheap O(n), fine at this size.
                stale = min(self._store.items(), key=lambda kv: kv[1].cached_at)
                self._store.pop(stale[0], None)

    async def take(self, key: _CacheKey) -> _SearchContext | None:
        """Read + delete the entry. Returns None when missing or stale."""
        async with self._lock:
            ctx = self._store.pop(key, None)
        if ctx is None:
            return None
        if time.monotonic() - ctx.cached_at > _CACHE_TTL_SECONDS:
            return None
        return ctx


# Module-level singleton — one cache per FastAPI process.
_CACHE = _SearchContextCache()

# Per-task identity for the current chat request. Set by the chat service
# at request entry; read by the web_search tool when it stashes a query.
# Using contextvars (rather than threading args through the agent + tool
# builders) keeps the agent surface untouched.
_CURRENT_USER: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_CURRENT_USER", default=None
)
_CURRENT_CONVERSATION: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_CURRENT_CONVERSATION", default=None
)


def bind_chat_request(*, user_id: str, conversation_id: str) -> None:
    """Attach user/conversation identity to the current async task.

    Called by ``ChatService`` at the start of each turn so the web_search
    tool can later stash a query into the cache without needing those
    identifiers in its signature.
    """
    _CURRENT_USER.set(user_id)
    _CURRENT_CONVERSATION.set(conversation_id)


def stash_search_context_for_current_chat(query: str, summary: str = "") -> bool:
    """Stash search context using the contextvar-bound identity.

    Returns False (and silently no-ops) when no chat request is currently
    bound — e.g. when the tool runs outside a chat path. Callers should
    treat the return value as informational.
    """
    user_id = _CURRENT_USER.get()
    conversation_id = _CURRENT_CONVERSATION.get()
    if not user_id or not conversation_id:
        return False
    stash_search_context(
        user_id=user_id,
        conversation_id=conversation_id,
        query=query,
        summary=summary,
    )
    return True


def stash_search_context(
    *,
    user_id: str,
    conversation_id: str,
    query: str,
    summary: str = "",
) -> asyncio.Task[None]:
    """Fire-and-forget cache write.

    Called from the agent / chat-service when a web_search tool was invoked
    on this turn. Returns the scheduled Task so callers can `await` it in
    tests; production callers can ignore the return value.
    """
    key = _CacheKey(user_id=user_id, conversation_id=conversation_id)
    ctx = _SearchContext(query=query, summary=summary, cached_at=time.monotonic())
    return asyncio.create_task(_CACHE.put(key, ctx))


async def take_prior_search_for(user_id: str, conversation_id: str) -> SearchContext | None:
    """Read+pop the cached search context for this conversation.

    Should be called by the chat service at request entry, *before* the
    agent runs (and potentially overwrites the entry for a new query).
    The caller threads the returned value into the post-turn classifier.
    """
    return await _CACHE.take(_CacheKey(user_id=user_id, conversation_id=conversation_id))


def _query_hash(query: str) -> str:
    return hashlib.md5(query.encode("utf-8")).hexdigest()[:12]


class SearchEngagementService:
    """Orchestrate the two-turn correlation + insight persistence."""

    def __init__(self, session: AsyncSession, embeddings: Embeddings) -> None:
        self._session = session
        self._embeddings = embeddings

    async def maybe_capture(
        self,
        *,
        llm: BaseChatModel,
        user_id: str,
        conversation_id: str,
        user_message: str,
        prior_search: SearchContext | None,
    ) -> bool:
        """Classify ``user_message`` against ``prior_search`` and persist on engaged.

        ``prior_search`` is the snapshot the chat service captured at
        request entry via :func:`take_prior_search_for` — passing it in
        explicitly avoids a TOCTOU race where the agent might stash a
        new entry during the same turn before this classifier runs.

        Returns True if a preference insight was persisted.
        """
        if prior_search is None:
            return False
        if time.monotonic() - prior_search.cached_at > _CACHE_TTL_SECONDS:
            return False

        try:
            signal = await chain.classify(
                search_query=prior_search.query,
                search_summary=prior_search.summary,
                user_followup_message=user_message,
            )
        except Exception:
            logger.exception(
                "Search-engagement classification failed user=%s conv=%s",
                user_id,
                conversation_id,
            )
            return False

        if not signal.is_engaged or not signal.derived_preference:
            return False
        if signal.confidence < chain.min_confidence:
            return False

        memory_service = MemoryService(session=self._session, embeddings=self._embeddings)
        try:
            await memory_service.store_insights(
                user_id=user_id,
                insights=[
                    {
                        "category": "preference",
                        "content": signal.derived_preference[:200],
                        "confidence": signal.confidence,
                    }
                ],
                source=f"web_search:{_query_hash(prior_search.query)}",
            )
        except Exception:
            logger.exception(
                "Search-engagement insight persist failed user=%s",
                user_id,
            )
            return False
        logger.info(
            "Search engagement captured user=%s conv=%s query=%r",
            user_id,
            conversation_id,
            prior_search.query,
        )
        return True
