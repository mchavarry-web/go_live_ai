"""Unit tests for the psych-profiling integration (DEV-98).

Covers, without a live DB or provider account:

  - normalization of Humantic AI and Sentino payloads into the shared
    OCEAN traits shape (0..1 floats + optional DISC)
  - the prompt section builder (empty when no profile is stored)
  - the service's env-gated no-op path: with no API keys configured,
    providers are skipped with a reason and nothing is upserted
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from app.config.settings import Settings
from app.prompts.avatar_prompts import _build_psych_profile_section
from app.services.psych_profile_service import (
    PsychProfileService,
    _to_unit_interval,
    normalize_humantic,
    normalize_sentino,
)


# ── Normalization: shared scale coercion ────────────────────────────────


class TestToUnitInterval:
    def test_passthrough_unit_scale(self):
        assert _to_unit_interval(0.73) == pytest.approx(0.73)

    def test_zero_to_ten_scale(self):
        assert _to_unit_interval(7.5) == pytest.approx(0.75)

    def test_zero_to_hundred_scale(self):
        assert _to_unit_interval(82) == pytest.approx(0.82)

    def test_nested_score_dict(self):
        assert _to_unit_interval({"score": 0.4}) == pytest.approx(0.4)

    def test_non_numeric_returns_none(self):
        assert _to_unit_interval("high") is None
        assert _to_unit_interval(None) is None
        assert _to_unit_interval(True) is None

    def test_negative_clamps_to_zero(self):
        assert _to_unit_interval(-3) == 0.0


# ── Normalization: Humantic AI ──────────────────────────────────────────


class TestNormalizeHumantic:
    def test_full_payload_with_disc(self):
        raw = {
            "results": {
                "personality_analysis": {
                    "ocean_assessment": {
                        "openness": {"score": 8.2},
                        "conscientiousness": {"score": 6.0},
                        "extraversion": {"score": 3.1},
                        "agreeableness": {"score": 7.7},
                        "neuroticism": {"score": 2.4},
                    },
                    "disc_assessment": {
                        "D": {"score": 7.0},
                        "I": {"score": 4.0},
                        "S": {"score": 5.5},
                        "C": {"score": 8.0},
                    },
                }
            }
        }
        traits = normalize_humantic(raw)
        assert traits is not None
        assert traits["openness"] == pytest.approx(0.82)
        assert traits["extraversion"] == pytest.approx(0.31)
        assert traits["neuroticism"] == pytest.approx(0.24)
        assert traits["disc"]["d"] == pytest.approx(0.70)
        assert traits["disc"]["c"] == pytest.approx(0.80)

    def test_payload_without_results_wrapper(self):
        raw = {
            "personality_analysis": {
                "ocean_assessment": {"openness": 0.9, "agreeableness": 0.2}
            }
        }
        traits = normalize_humantic(raw)
        assert traits == {
            "openness": pytest.approx(0.9),
            "agreeableness": pytest.approx(0.2),
        }

    def test_unrecognized_payload_returns_none(self):
        assert normalize_humantic({"foo": "bar"}) is None
        assert normalize_humantic({}) is None
        assert normalize_humantic("not a dict") is None  # type: ignore[arg-type]


# ── Normalization: Sentino ──────────────────────────────────────────────


class TestNormalizeSentino:
    def test_prefixed_scoring_keys(self):
        raw = {
            "scoring": {
                "big5_openness": {"score": 0.71},
                "big5_conscientiousness": {"score": 0.55},
                "big5_extraversion": {"score": 0.12},
                "big5_agreeableness": {"score": 0.88},
                "big5_neuroticism": {"score": 0.33},
            }
        }
        traits = normalize_sentino(raw)
        assert traits is not None
        assert traits["openness"] == pytest.approx(0.71)
        assert traits["agreeableness"] == pytest.approx(0.88)
        assert "disc" not in traits

    def test_nested_big5_block(self):
        raw = {"scoring": {"big5": {"openness": 0.6, "neuroticism": 0.4}}}
        traits = normalize_sentino(raw)
        assert traits == {
            "openness": pytest.approx(0.6),
            "neuroticism": pytest.approx(0.4),
        }

    def test_bare_top_level_traits(self):
        traits = normalize_sentino({"extraversion": 0.5})
        assert traits == {"extraversion": pytest.approx(0.5)}

    def test_unrecognized_payload_returns_none(self):
        assert normalize_sentino({"scoring": {}}) is None
        assert normalize_sentino({}) is None


# ── Prompt section builder ──────────────────────────────────────────────


class TestPsychProfileSection:
    def test_empty_when_no_profile(self):
        assert _build_psych_profile_section(None) == ""
        assert _build_psych_profile_section({}) == ""

    def test_empty_when_traits_have_no_known_keys(self):
        assert _build_psych_profile_section({"humantic": {"foo": 0.5}}) == ""

    def test_renders_one_line_per_trait(self):
        section = _build_psych_profile_section(
            {
                "sentino": {
                    "openness": 0.9,
                    "conscientiousness": 0.5,
                    "extraversion": 0.1,
                    "agreeableness": 0.8,
                    "neuroticism": 0.2,
                }
            }
        )
        assert section.startswith("PERFIL PSICOLÓGICO (uso interno")
        assert "Apertura" in section
        assert "Extraversión" in section
        # high openness → "abierto", low extraversion → "introvertido"
        assert "abierto/a a ideas nuevas" in section
        assert "introvertido/a" in section
        # Mode block always wins.
        assert "MODO ACTIVO siempre tiene prioridad" in section

    def test_averages_across_providers(self):
        section = _build_psych_profile_section(
            {
                "humantic": {"openness": 1.0},
                "sentino": {"openness": 0.0},
            }
        )
        # avg 0.5 → the medium description.
        assert "Se abre a ideas nuevas sin perder el piso práctico." in section

    def test_disc_line_from_humantic(self):
        section = _build_psych_profile_section(
            {
                "humantic": {
                    "openness": 0.5,
                    "disc": {"d": 0.9, "i": 0.2, "s": 0.3, "c": 0.4},
                }
            }
        )
        assert "Estilo DISC dominante: dominancia" in section


# ── Service: env-gated no-op without keys ───────────────────────────────


def _build_service(settings: Settings) -> PsychProfileService:
    service = PsychProfileService.__new__(PsychProfileService)
    service._session = MagicMock()
    service._settings = settings
    service.repository = MagicMock()
    service.repository.upsert = AsyncMock()
    service.repository.list_for_user = AsyncMock(return_value=[])
    return service


class TestServiceNoOpWithoutKeys:
    @pytest.mark.asyncio
    async def test_no_keys_skips_both_providers(self, settings: Settings):
        assert settings.humantic_api_key is None
        assert settings.sentino_api_key is None
        service = _build_service(settings)

        profiles, errors = await service.run_profiling(
            user_id="user-1",
            text_corpus="hola, soy un corpus de prueba",
        )

        assert profiles == {"humantic": None, "sentino": None}
        assert errors == {
            "humantic": "api_key_not_configured",
            "sentino": "api_key_not_configured",
        }
        service.repository.upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_provider_subset_respected(self, settings: Settings):
        service = _build_service(settings)
        profiles, errors = await service.run_profiling(
            user_id="user-1",
            text_corpus="hola",
            providers=["sentino"],
        )
        assert list(profiles) == ["sentino"]
        assert errors == {"sentino": "api_key_not_configured"}

    @pytest.mark.asyncio
    async def test_missing_input_reported_when_key_present(
        self, settings: Settings
    ):
        settings_with_key = settings.model_copy(
            update={"sentino_api_key": SecretStr("sk-sentino-test")}
        )
        service = _build_service(settings_with_key)
        profiles, errors = await service.run_profiling(
            user_id="user-1",
            providers=["sentino"],
        )
        assert profiles == {"sentino": None}
        assert errors == {"sentino": "no_input_provided"}
        service.repository.upsert.assert_not_awaited()
