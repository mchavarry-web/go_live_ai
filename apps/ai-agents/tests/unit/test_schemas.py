"""Unit tests for Pydantic schemas.

Validates that all Pydantic models enforce their constraints correctly,
including field validation, type coercion, and immutability.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.enums import InsightCategory
from app.models.schemas import (
    ChatGenerateRequest,
    ChatGenerateResponse,
    HealthCheckResponse,
    Insight,
    InsightExtractRequest,
    MemoryResponse,
    SemanticSearchRequest,
    SentimentAnalysis,
    UserProfile,
)


class TestUserProfile:
    """Tests for UserProfile schema."""

    def test_valid_profile(self) -> None:
        """Test creating a valid user profile."""
        profile = UserProfile(
            display_name="Juan Pérez",
            avatar_name="Juanito",
            age_range="25_34",
            interests=["tecnología", "fútbol"],
            knowledge_level=3,
        )
        assert profile.display_name == "Juan Pérez"
        assert profile.avatar_name == "Juanito"
        assert profile.age_range == "25_34"
        assert profile.knowledge_level == 3

    def test_interests_are_lowercase_and_unique(self) -> None:
        """Test that interests are normalized to lowercase and deduplicated."""
        profile = UserProfile(
            display_name="Test",
            avatar_name="Testy",
            interests=["TECH", "tech", "Music", " music "],
        )
        assert set(profile.interests) == {"tech", "music"}

    def test_frozen_profile_prevents_mutation(self) -> None:
        """Test that frozen config prevents attribute assignment."""
        profile = UserProfile(
            display_name="Test",
            avatar_name="Testy",
        )
        with pytest.raises(ValidationError):
            profile.display_name = "Changed"  # type: ignore[misc]

    def test_whitespace_is_stripped(self) -> None:
        """Test that whitespace is stripped from string fields."""
        profile = UserProfile(
            display_name="  Juan  ",
            avatar_name=" Juanito ",
        )
        assert profile.display_name == "Juan"
        assert profile.avatar_name == "Juanito"

    def test_empty_display_name_fails(self) -> None:
        """Test that empty display_name is rejected."""
        with pytest.raises(ValidationError):
            UserProfile(display_name="", avatar_name="Test")

    def test_knowledge_level_bounds(self) -> None:
        """Test that knowledge_level must be between 1 and 10.

        Range was widened from 1-5 to 1-10 in Phase 9 when Rails'
        Avatar.knowledge_level (log-scaled, multi-signal) became canonical.
        """
        with pytest.raises(ValidationError):
            UserProfile(
                display_name="Test",
                avatar_name="Testy",
                knowledge_level=0,
            )
        with pytest.raises(ValidationError):
            UserProfile(
                display_name="Test",
                avatar_name="Testy",
                knowledge_level=11,
            )
        # Mid-range values that were illegal under the old 1-5 cap must now pass.
        for k in (6, 8, 10):
            UserProfile(
                display_name="Test",
                avatar_name="Testy",
                knowledge_level=k,
            )

    def test_default_values(self) -> None:
        """Test default values for optional fields."""
        profile = UserProfile(
            display_name="Test",
            avatar_name="Testy",
        )
        assert profile.age_range is None
        assert profile.country is None
        assert profile.interests == []
        assert profile.knowledge_level == 1


class TestChatGenerateRequest:
    """Tests for ChatGenerateRequest schema."""

    def test_valid_request(self) -> None:
        """Test creating a valid chat request."""
        profile = UserProfile(display_name="Test", avatar_name="Testy")
        request = ChatGenerateRequest(
            user_id="user-123",
            message="Hello, how are you?",
            conversation_id="conv-456",
            user_profile=profile,
        )
        assert request.user_id == "user-123"
        assert request.message == "Hello, how are you?"
        assert request.conversation_history == []

    def test_empty_message_fails(self) -> None:
        """Test that empty message is rejected."""
        profile = UserProfile(display_name="Test", avatar_name="Testy")
        with pytest.raises(ValidationError):
            ChatGenerateRequest(
                user_id="user-123",
                message="",
                conversation_id="conv-456",
                user_profile=profile,
            )

    def test_optional_fields_default_none(self) -> None:
        """Test that optional fields default to None."""
        profile = UserProfile(display_name="Test", avatar_name="Testy")
        request = ChatGenerateRequest(
            user_id="user-123",
            message="Hi",
            conversation_id="conv-456",
            user_profile=profile,
        )
        assert request.social_data is None
        assert request.health_data is None


class TestChatGenerateResponse:
    """Tests for ChatGenerateResponse schema."""

    def test_minimal_response(self) -> None:
        """Test creating a minimal valid response."""
        response = ChatGenerateResponse(response="Hola, ¿cómo estás?")
        assert response.response == "Hola, ¿cómo estás?"
        assert response.emotion_detected is None
        assert response.new_insights == []
        assert response.tokens_used == 0

    def test_negative_tokens_fails(self) -> None:
        """Test that negative tokens_used is rejected."""
        with pytest.raises(ValidationError):
            ChatGenerateResponse(response="Hi", tokens_used=-1)


class TestInsight:
    """Tests for Insight schema."""

    def test_valid_insight(self) -> None:
        """Test creating a valid insight."""
        insight = Insight(
            id="insight-123",
            user_id="user-456",
            category=InsightCategory.PREFERENCE,
            content="Le gusta el café por las mañanas",
            confidence=0.85,
            source="conversation",
            created_at=datetime.now(tz=timezone.utc),
        )
        assert insight.category == InsightCategory.PREFERENCE
        assert insight.confidence == 0.85

    def test_confidence_bounds(self) -> None:
        """Test that confidence must be between 0.0 and 1.0."""
        with pytest.raises(ValidationError):
            Insight(
                id="1",
                user_id="u1",
                category=InsightCategory.GOAL,
                content="test",
                confidence=1.5,
                source="test",
            )

    def test_content_max_length(self) -> None:
        """Test that content exceeding 1000 chars is rejected."""
        with pytest.raises(ValidationError):
            Insight(
                id="1",
                user_id="u1",
                category=InsightCategory.EMOTION,
                content="x" * 1001,
                confidence=0.5,
                source="test",
            )


class TestInsightExtractRequest:
    """Tests for InsightExtractRequest schema."""

    def test_valid_request(self) -> None:
        """Test creating a valid extract request."""
        request = InsightExtractRequest(
            user_id="user-123",
            message="Me encanta correr por las mañanas",
            context="El usuario practica deportes",
        )
        assert request.user_id == "user-123"
        assert request.context == "El usuario practica deportes"

    def test_default_context(self) -> None:
        """Test that context defaults to empty string."""
        request = InsightExtractRequest(
            user_id="user-123",
            message="Hola",
        )
        assert request.context == ""


class TestMemoryResponse:
    """Tests for MemoryResponse schema."""

    def test_default_values(self) -> None:
        """Test default values."""
        response = MemoryResponse(user_id="user-123")
        assert response.total_insights == 0
        assert response.knowledge_level == 1
        assert response.insights == []


class TestSentimentAnalysis:
    """Tests for SentimentAnalysis schema."""

    def test_valid_sentiment(self) -> None:
        """Test creating a valid sentiment analysis."""
        from app.models.enums import Sentiment

        analysis = SentimentAnalysis(
            sentiment=Sentiment.POSITIVE,
            primary_emotion="alegría",
            intensity=0.8,
            message="Estoy muy contento hoy",
        )
        assert analysis.sentiment == Sentiment.POSITIVE
        assert analysis.intensity == 0.8


class TestSemanticSearchRequest:
    """Tests for SemanticSearchRequest schema."""

    def test_valid_request(self) -> None:
        """Test creating a valid search request."""
        request = SemanticSearchRequest(
            user_id="user-123",
            query="What are my hobbies?",
        )
        assert request.top_k == 5
        assert request.categories is None

    def test_top_k_bounds(self) -> None:
        """Test that top_k must be between 1 and 50."""
        with pytest.raises(ValidationError):
            SemanticSearchRequest(
                user_id="user-123",
                query="test",
                top_k=0,
            )
        with pytest.raises(ValidationError):
            SemanticSearchRequest(
                user_id="user-123",
                query="test",
                top_k=51,
            )


class TestHealthCheckResponse:
    """Tests for HealthCheckResponse schema."""

    def test_healthy_response(self) -> None:
        """Test creating a healthy status response."""
        response = HealthCheckResponse(
            status="healthy",
            version="0.1.0",
            environment="development",
            database="connected",
            langsmith="enabled",
        )
        assert response.status == "healthy"
        assert response.version == "0.1.0"

    def test_default_values(self) -> None:
        """Test default values for optional dependency statuses."""
        response = HealthCheckResponse(
            status="healthy",
            version="0.1.0",
            environment="development",
        )
        assert response.database == "disconnected"
        assert response.langsmith == "disabled"
