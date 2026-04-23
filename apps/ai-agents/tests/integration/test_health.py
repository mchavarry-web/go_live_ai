"""Integration tests for the health check endpoint.

Verifies that the /health endpoint responds correctly and reports
the status of service dependencies.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Integration tests for GET /health."""

    async def test_health_returns_200(self, async_client: AsyncClient) -> None:
        """Test that the health endpoint returns HTTP 200."""
        response = await async_client.get("/health")
        assert response.status_code == 200

    async def test_health_response_structure(self, async_client: AsyncClient) -> None:
        """Test that the health response contains required fields."""
        response = await async_client.get("/health")
        data = response.json()

        assert "status" in data
        assert "version" in data
        assert "environment" in data
        assert "database" in data
        assert "langsmith" in data

    async def test_health_reports_version(self, async_client: AsyncClient) -> None:
        """Test that the health endpoint reports the correct version."""
        response = await async_client.get("/health")
        data = response.json()

        assert data["version"] == "0.1.0"

    async def test_health_status_is_healthy(self, async_client: AsyncClient) -> None:
        """Test that the service reports healthy status."""
        response = await async_client.get("/health")
        data = response.json()

        assert data["status"] == "healthy"
