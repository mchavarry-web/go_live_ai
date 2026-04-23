"""Shared-secret auth for internal routes.

The FastAPI ai-agents service is never exposed to clients directly. Only the
Rails backend calls it, and every request must carry a matching
``X-Internal-Token`` header. ``/health`` remains public for liveness probes.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.config.settings import Settings
from app.api.deps import get_settings


async def require_internal_token(
    x_internal_token: str | None = Header(default=None),
) -> None:
    """Reject requests that do not present the shared Rails ↔ FastAPI secret.

    Uses ``secrets.compare_digest`` to avoid timing attacks.

    Raises:
        HTTPException: 401 if the header is missing or does not match the
            configured ``internal_token`` in ``Settings``.
    """
    settings: Settings = get_settings()
    expected = getattr(settings, "internal_token", None)

    if not expected:
        # Fail closed: if no token is configured the service refuses internal calls.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_TOKEN not configured",
        )

    if not x_internal_token or not secrets.compare_digest(
        x_internal_token, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token",
        )
