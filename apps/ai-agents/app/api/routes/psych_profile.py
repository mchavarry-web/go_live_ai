"""Psychological profiling endpoints (DEV-98, 2026-08-15).

Env-gated Humantic AI + Sentino integration. Rails owns the opt-in gate
(``avatar.behavior["psych_profiling_opt_in"]``) and never calls these
endpoints for a user who hasn't opted in; this service additionally
no-ops per provider when its API key is unset.

Endpoints:
    POST /internal/profile/psych            - Run providers + upsert profiles.
    GET  /internal/profile/psych/{user_id}  - Read stored profiles.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import DbSessionDep, SettingsDep
from app.services.psych_profile_service import PROVIDERS, PsychProfileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/profile", tags=["Psych Profile"])


# ── Request/Response schemas ────────────────────────────────────────────


class PsychProfileRequest(BaseModel):
    """Request to run psychological profiling for a user."""

    user_id: str = Field(..., min_length=1, max_length=36)
    text_corpus: str | None = Field(default=None, max_length=100_000)
    linkedin_url: str | None = Field(default=None, max_length=500)
    providers: list[str] | None = Field(
        default=None,
        description="Subset of providers to run; defaults to all.",
    )


class PsychProfileRunResponse(BaseModel):
    """Result of a profiling run — per-provider traits and skip/error reasons."""

    user_id: str
    profiles: dict[str, dict | None]
    errors: dict[str, str]


class PsychProfileStoredResponse(BaseModel):
    """Stored profiles for a user, keyed by provider."""

    user_id: str
    profiles: dict[str, dict]


# ── Endpoints ───────────────────────────────────────────────────────────


@router.post(
    "/psych",
    response_model=PsychProfileRunResponse,
    summary="Run psychological profiling",
    description=(
        "Runs the available providers (Humantic AI, Sentino) concurrently "
        "over the supplied text corpus and/or LinkedIn URL, upserting one "
        "row per (user, provider). Providers with no API key configured "
        "are reported in `errors` and skipped — with no keys set this "
        "endpoint is a clean no-op."
    ),
)
async def run_psych_profiling(
    body: PsychProfileRequest,
    settings: SettingsDep,
    session: DbSessionDep,
) -> PsychProfileRunResponse:
    """Run profiling providers and persist normalized trait profiles."""
    if body.providers:
        unknown = [p for p in body.providers if p not in PROVIDERS]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown providers: {', '.join(unknown)}",
            )
    try:
        service = PsychProfileService(session=session, settings=settings)
        profiles, errors = await service.run_profiling(
            user_id=body.user_id,
            text_corpus=body.text_corpus,
            linkedin_url=body.linkedin_url,
            providers=body.providers,
        )
        return PsychProfileRunResponse(
            user_id=body.user_id,
            profiles=profiles,
            errors=errors,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Psych profiling failed for user_id=%s", body.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Psych profiling failed. Please try again.",
        ) from exc


@router.get(
    "/psych/{user_id}",
    response_model=PsychProfileStoredResponse,
    summary="Get stored psych profiles",
    description="Returns the stored normalized profiles per provider for a user.",
)
async def get_psych_profiles(
    user_id: str,
    settings: SettingsDep,
    session: DbSessionDep,
) -> PsychProfileStoredResponse:
    """Read stored psych profiles for a user."""
    try:
        service = PsychProfileService(session=session, settings=settings)
        profiles = await service.get_profiles(user_id)
        return PsychProfileStoredResponse(user_id=user_id, profiles=profiles)
    except Exception as exc:
        logger.exception("Psych profile read failed for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve psych profiles.",
        ) from exc
