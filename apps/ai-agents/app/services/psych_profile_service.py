"""Psychological profiling via external providers (DEV-98, 2026-08-15).

Two providers, both env-gated and both normalized into the SAME traits
shape so downstream consumers (prompt builder, Rails proxy) never branch
on provider:

    {
        "openness": 0.0-1.0,
        "conscientiousness": 0.0-1.0,
        "extraversion": 0.0-1.0,
        "agreeableness": 0.0-1.0,
        "neuroticism": 0.0-1.0,
        "disc": {"d": ..., "i": ..., "s": ..., "c": ...},  # optional, Humantic only
    }

Providers:
    - Humantic AI — analysis by LinkedIn URL or raw text corpus.
    - Sentino — big-five scoring of a text corpus.

The endpoint URLs / params below are implemented from general knowledge
of the provider APIs and are intentionally kept in module constants so
they are trivial to correct against the real API docs. A provider with
no configured API key returns None (logged, never raises) — with no keys
set the whole feature no-ops cleanly.
"""

import asyncio
import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.repositories.psych_profile_repository import PsychProfileRepository

logger = logging.getLogger(__name__)

# ── Provider endpoint constants (verify against real API docs) ──────────
#
# Humantic AI: profile creation + fetch. The key travels as an `apikey`
# query param. A LinkedIn URL doubles as the analysis id; for raw text we
# create the profile under the user's own id with the corpus in the body.
HUMANTIC_API_BASE = "https://api.humantic.ai/v1"
HUMANTIC_FETCH_ENDPOINT = f"{HUMANTIC_API_BASE}/user-profile"
HUMANTIC_CREATE_ENDPOINT = f"{HUMANTIC_API_BASE}/user-profile/create"
HUMANTIC_API_KEY_PARAM = "apikey"

# Sentino: single scoring call, Bearer-key auth, body {text, inventories}.
SENTINO_SCORE_ENDPOINT = "https://api.sentino.org/api/score"
SENTINO_INVENTORIES = ["big5"]

_HTTP_TIMEOUT_SECONDS = 60.0

PROVIDERS = ("humantic", "sentino")

_OCEAN_TRAITS = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
)

# Truncate outbound corpora defensively — providers cap payload sizes and
# a runaway corpus should never 413 the whole profiling run.
_MAX_CORPUS_CHARS = 20_000


def _to_unit_interval(value: Any) -> float | None:
    """Coerce a provider score onto 0..1.

    Providers disagree on scales: Sentino scores are already 0..1,
    Humantic assessments commonly arrive on 0..10 or 0..100. Heuristic:
    ≤1 passes through, ≤10 divides by 10, otherwise divides by 100.
    """
    if isinstance(value, dict):
        # Nested {"score": x} / {"quantile": x} shapes.
        value = value.get("score", value.get("quantile"))
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    v = float(value)
    if v < 0:
        return 0.0
    if v <= 1.0:
        return v
    if v <= 10.0:
        return v / 10.0
    return min(v / 100.0, 1.0)


def normalize_humantic(raw: dict) -> dict | None:
    """Normalize a Humantic AI profile response into the shared traits shape.

    Assumed response shape (verify against docs):
        {"results": {"personality_analysis": {
            "ocean_assessment": {"openness": {"score": ...}, ...},
            "disc_assessment": {"d": ..., "i": ..., "s": ..., "c": ...}}}}
    Falls back to top-level "personality_analysis" when "results" is absent.

    Returns None when no OCEAN trait could be extracted.
    """
    if not isinstance(raw, dict):
        return None
    analysis = raw.get("results", raw)
    if isinstance(analysis, dict):
        analysis = analysis.get("personality_analysis", analysis)
    if not isinstance(analysis, dict):
        return None

    ocean = analysis.get("ocean_assessment", analysis)
    traits: dict[str, Any] = {}
    for trait in _OCEAN_TRAITS:
        score = _to_unit_interval(ocean.get(trait)) if isinstance(ocean, dict) else None
        if score is not None:
            traits[trait] = score
    if not traits:
        return None

    disc_raw = analysis.get("disc_assessment")
    if isinstance(disc_raw, dict):
        disc = {}
        for key, value in disc_raw.items():
            score = _to_unit_interval(value)
            if score is not None:
                disc[str(key).lower()] = score
        if disc:
            traits["disc"] = disc
    return traits


def normalize_sentino(raw: dict) -> dict | None:
    """Normalize a Sentino score response into the shared traits shape.

    Assumed response shape (verify against docs):
        {"scoring": {"big5_openness": {"score": 0.7, ...}, ...}}
    Also tolerates {"scoring": {"big5": {"openness": ...}}} and bare
    top-level trait keys.

    Returns None when no OCEAN trait could be extracted.
    """
    if not isinstance(raw, dict):
        return None
    scoring = raw.get("scoring", raw)
    if isinstance(scoring, dict) and isinstance(scoring.get("big5"), dict):
        scoring = scoring["big5"]
    if not isinstance(scoring, dict):
        return None

    traits: dict[str, Any] = {}
    for trait in _OCEAN_TRAITS:
        value = scoring.get(trait, scoring.get(f"big5_{trait}"))
        score = _to_unit_interval(value)
        if score is not None:
            traits[trait] = score
    return traits or None


class PsychProfileService:
    """Runs available profiling providers and persists normalized results.

    Providers run concurrently; each degrades independently — a missing
    API key, HTTP failure, or unparseable payload for one provider never
    blocks the other. Nothing here is called at chat time; chat only
    reads previously stored rows.
    """

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self.repository = PsychProfileRepository(session)

    # ── Public API ──────────────────────────────────────────────────────

    async def run_profiling(
        self,
        *,
        user_id: str,
        text_corpus: str | None = None,
        linkedin_url: str | None = None,
        providers: list[str] | None = None,
    ) -> tuple[dict[str, dict | None], dict[str, str]]:
        """Run the requested providers concurrently and upsert results.

        Returns:
            (profiles, errors) — ``profiles`` maps provider → normalized
            traits (or None when the provider produced nothing);
            ``errors`` maps provider → short reason string for skips and
            failures (missing key, missing input, HTTP error, ...).
        """
        requested = [p for p in (providers or list(PROVIDERS)) if p in PROVIDERS]
        if text_corpus:
            text_corpus = text_corpus[:_MAX_CORPUS_CHARS]

        results = await asyncio.gather(
            *[
                self._run_provider(
                    provider,
                    user_id=user_id,
                    text_corpus=text_corpus,
                    linkedin_url=linkedin_url,
                )
                for provider in requested
            ],
            return_exceptions=True,
        )

        profiles: dict[str, dict | None] = {}
        errors: dict[str, str] = {}
        for provider, result in zip(requested, results):
            if isinstance(result, BaseException):
                logger.exception(
                    "Psych profiling failed provider=%s user_id=%s",
                    provider,
                    user_id,
                    exc_info=result,
                )
                profiles[provider] = None
                errors[provider] = f"{type(result).__name__}: {result}"
                continue
            traits, error = result
            profiles[provider] = traits
            if error:
                errors[provider] = error
        return profiles, errors

    async def get_profiles(self, user_id: str) -> dict[str, dict]:
        """Return stored profiles as {provider: {traits, source_summary, ...}}."""
        rows = await self.repository.list_for_user(user_id)
        return {
            row.provider: {
                "traits": row.traits,
                "source_summary": row.source_summary,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        }

    # ── Provider orchestration ──────────────────────────────────────────

    async def _run_provider(
        self,
        provider: str,
        *,
        user_id: str,
        text_corpus: str | None,
        linkedin_url: str | None,
    ) -> tuple[dict | None, str | None]:
        """Run one provider end-to-end: fetch → normalize → upsert.

        Returns (traits, error_reason). A disabled provider (no API key)
        returns (None, "api_key_not_configured") without raising.
        """
        if provider == "humantic":
            raw = await self._fetch_humantic(
                user_id=user_id,
                text_corpus=text_corpus,
                linkedin_url=linkedin_url,
            )
            normalize = normalize_humantic
        else:
            raw = await self._fetch_sentino(text_corpus=text_corpus)
            normalize = normalize_sentino

        if isinstance(raw, str):
            # Skip/error reason from the fetcher (no key, missing input, HTTP).
            return None, raw
        if raw is None:
            return None, "empty_provider_response"

        traits = normalize(raw)
        if traits is None:
            logger.warning(
                "Psych profiling: could not normalize %s response user_id=%s",
                provider,
                user_id,
            )
            return None, "unrecognized_response_shape"

        source_summary = (
            f"linkedin:{linkedin_url}"
            if provider == "humantic" and linkedin_url
            else f"text_corpus:{len(text_corpus or '')} chars"
        )
        await self.repository.upsert(
            user_id=user_id,
            provider=provider,
            traits=traits,
            raw=raw,
            source_summary=source_summary,
        )
        logger.info(
            "Psych profile stored provider=%s user_id=%s traits=%s",
            provider,
            user_id,
            sorted(k for k in traits if k != "disc"),
        )
        return traits, None

    # ── Thin async httpx provider clients ───────────────────────────────

    async def _fetch_humantic(
        self,
        *,
        user_id: str,
        text_corpus: str | None,
        linkedin_url: str | None,
    ) -> dict | str | None:
        """Call Humantic AI. Returns raw dict, or a str skip/error reason."""
        key = self._settings.humantic_api_key
        if key is None or not key.get_secret_value():
            logger.info("Humantic AI disabled: no API key configured")
            return "api_key_not_configured"
        if not linkedin_url and not text_corpus:
            return "no_input_provided"

        api_key = key.get_secret_value()
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
                if linkedin_url:
                    # LinkedIn URL doubles as the analysis id; fetch triggers
                    # (or returns) the analysis for that id.
                    response = await client.get(
                        HUMANTIC_FETCH_ENDPOINT,
                        params={
                            HUMANTIC_API_KEY_PARAM: api_key,
                            "id": linkedin_url,
                        },
                    )
                else:
                    # Text-corpus analysis: create under the user's own id,
                    # then fetch the computed profile.
                    create = await client.post(
                        HUMANTIC_CREATE_ENDPOINT,
                        params={
                            HUMANTIC_API_KEY_PARAM: api_key,
                            "id": user_id,
                        },
                        json={"text": text_corpus},
                    )
                    if create.status_code >= 400:
                        logger.warning(
                            "Humantic create failed http=%d body=%.300s",
                            create.status_code,
                            create.text,
                        )
                        return f"http_{create.status_code}"
                    response = await client.get(
                        HUMANTIC_FETCH_ENDPOINT,
                        params={
                            HUMANTIC_API_KEY_PARAM: api_key,
                            "id": user_id,
                        },
                    )
        except httpx.HTTPError as exc:
            logger.warning("Humantic request failed: %s", exc)
            return f"request_error:{type(exc).__name__}"

        if response.status_code >= 400:
            logger.warning(
                "Humantic fetch failed http=%d body=%.300s",
                response.status_code,
                response.text,
            )
            return f"http_{response.status_code}"
        try:
            return response.json()
        except ValueError:
            return "invalid_json_response"

    async def _fetch_sentino(
        self, *, text_corpus: str | None
    ) -> dict | str | None:
        """Call Sentino. Returns raw dict, or a str skip/error reason."""
        key = self._settings.sentino_api_key
        if key is None or not key.get_secret_value():
            logger.info("Sentino disabled: no API key configured")
            return "api_key_not_configured"
        if not text_corpus:
            return "no_input_provided"

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    SENTINO_SCORE_ENDPOINT,
                    headers={
                        "Authorization": f"Bearer {key.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "text": text_corpus,
                        "inventories": SENTINO_INVENTORIES,
                    },
                )
        except httpx.HTTPError as exc:
            logger.warning("Sentino request failed: %s", exc)
            return f"request_error:{type(exc).__name__}"

        if response.status_code >= 400:
            logger.warning(
                "Sentino score failed http=%d body=%.300s",
                response.status_code,
                response.text,
            )
            return f"http_{response.status_code}"
        try:
            return response.json()
        except ValueError:
            return "invalid_json_response"
