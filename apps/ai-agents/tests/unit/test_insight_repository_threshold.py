"""Unit tests for ``InsightRepository.search_similar`` distance threshold.

Wave A.2 (2026-05-06). The repository gained an optional ``max_distance``
parameter that adds a ``WHERE cosine_distance(embedding, q) <= max_distance``
predicate before the LIMIT. These tests verify the SQL goes out the door
with the right shape; we don't need a live Postgres for that.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.database import InsightModel
from app.repositories.insight_repository import InsightRepository


def _build_repo():
    session = MagicMock()
    # ``execute`` is awaitable in async SQLAlchemy. Return a mock whose
    # .scalars().all() yields no rows — we're only inspecting the SQL.
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    return InsightRepository(session=session), session


def _executed_stmt(session) -> str:
    """Render the SQL of the last execute() call."""
    [stmt], _ = session.execute.call_args
    return str(stmt.compile(compile_kwargs={"literal_binds": False}))


@pytest.mark.asyncio
async def test_max_distance_adds_where_clause() -> None:
    """When max_distance is set, the SQL includes the cosine-distance predicate."""
    repo, session = _build_repo()

    await repo.search_similar(
        user_id="u1",
        query_embedding=[0.0] * 1536,
        max_distance=0.40,
    )

    sql = _executed_stmt(session)
    assert "cosine_distance" in sql or "<=>" in sql, sql
    # Two appearances are expected: one in WHERE, one in ORDER BY.
    occurrences = sql.lower().count("cosine_distance") + sql.count("<=>")
    assert occurrences >= 2, sql


@pytest.mark.asyncio
async def test_no_max_distance_omits_the_predicate() -> None:
    """When max_distance is None, the SQL does NOT add a distance filter."""
    repo, session = _build_repo()

    await repo.search_similar(
        user_id="u1",
        query_embedding=[0.0] * 1536,
    )

    sql = _executed_stmt(session)
    # ORDER BY still uses cosine_distance, but there should be no WHERE on
    # it. We detect this by counting: with no threshold, only the ORDER BY
    # reference exists (one occurrence).
    occurrences = sql.lower().count("cosine_distance") + sql.count("<=>")
    assert occurrences == 1, sql


@pytest.mark.asyncio
async def test_categories_and_sources_still_apply() -> None:
    """SQL still includes category/source filters alongside max_distance."""
    repo, session = _build_repo()

    await repo.search_similar(
        user_id="u1",
        query_embedding=[0.0] * 1536,
        categories=["preference"],
        sources=["conversation"],
        max_distance=0.40,
    )

    sql = _executed_stmt(session)
    assert "category" in sql.lower()
    assert "source" in sql.lower()
    assert "user_id" in sql.lower()
