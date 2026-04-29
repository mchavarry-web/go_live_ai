"""Unit tests for avatar mode behavior.

Three modes drive the avatar's prompt block, dialect-mirroring rules, and
persona-evolution scoping. The Citas mode further internally branches by
``mode_message_count`` (lifetime user messages in dating mode).
"""

import pytest
from pydantic import ValidationError

from app.models.schemas import UserProfile
from app.prompts.avatar_prompts import (
    _build_behavior_section,
    _build_language_style_section,
    _build_mode_section,
    build_avatar_system_prompt,
)


class TestModeSection:
    """``_build_mode_section`` returns the right block per mode."""

    def test_professional_block_forbids_dialect(self) -> None:
        out = _build_mode_section("professional", 0)
        assert "PROFESIONAL" in out
        assert "NO uses jerga regional" in out
        assert "NO uses voseo" in out
        # No accidental "casual" leaking through
        assert "Tono casual" not in out

    def test_friends_block_allows_colloquialism(self) -> None:
        out = _build_mode_section("friends", 0)
        assert "AMIGOS" in out
        assert "Tono casual permitido" in out

    def test_dating_nascent_when_count_below_30(self) -> None:
        for c in (0, 1, 29):
            out = _build_mode_section("dating", c)
            assert "etapa inicial" in out, f"count={c} did not pick nascent"
            assert "NO uses apodos" in out

    def test_dating_warming_at_30_to_149(self) -> None:
        for c in (30, 100, 149):
            out = _build_mode_section("dating", c)
            assert "etapa media" in out, f"count={c} did not pick warming"

    def test_dating_established_at_150_plus(self) -> None:
        for c in (150, 500, 10_000):
            out = _build_mode_section("dating", c)
            assert "etapa establecida" in out, f"count={c} did not pick established"

    def test_unknown_mode_falls_back_to_friends(self) -> None:
        out = _build_mode_section("not_a_real_mode", 0)
        assert "AMIGOS" in out


class TestBuildAvatarSystemPromptWithMode:
    """The mode block lands inside the full system prompt."""

    def test_professional_anchors_at_top_of_prompt(self) -> None:
        out = build_avatar_system_prompt(
            avatar_name="Avatar",
            display_name="Augusto",
            active_mode="professional",
            mode_message_count=0,
        )
        # Mode block should sit BEFORE the personality / insights sections
        prof_idx = out.index("MODO ACTIVO: PROFESIONAL")
        sobre_ti_idx = out.index("SOBRE TI")
        assert prof_idx < sobre_ti_idx, "mode block must precede SOBRE TI"

    def test_dating_picks_warming_block_at_50_messages(self) -> None:
        out = build_avatar_system_prompt(
            avatar_name="Avatar",
            display_name="Augusto",
            active_mode="dating",
            mode_message_count=50,
        )
        assert "etapa media" in out
        assert "etapa inicial" not in out

    def test_default_mode_is_friends(self) -> None:
        # Omit active_mode entirely
        out = build_avatar_system_prompt(
            avatar_name="Avatar",
            display_name="Augusto",
        )
        assert "MODO ACTIVO: AMIGOS" in out


class TestUserProfileMode:
    """The Pydantic schema accepts and validates the new fields."""

    def test_active_mode_defaults_to_friends(self) -> None:
        p = UserProfile(display_name="A", avatar_name="B")
        assert p.active_mode == "friends"
        assert p.mode_message_count == 0

    def test_active_mode_accepts_three_values(self) -> None:
        for m in ("professional", "friends", "dating"):
            p = UserProfile(display_name="A", avatar_name="B", active_mode=m)
            assert p.active_mode == m

    def test_active_mode_rejects_unknown_value(self) -> None:
        with pytest.raises(ValidationError):
            UserProfile(display_name="A", avatar_name="B", active_mode="chaos")

    def test_mode_message_count_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            UserProfile(display_name="A", avatar_name="B", mode_message_count=-1)


class TestModeSuppressesConflictingSections:
    """Strict modes (professional, dating-nascent) must suppress the
    dialect catalog and tone overrides that would otherwise contradict
    the mode block. ``language`` and ``restricted_topics`` always pass
    through because they're policy, not register."""

    def test_language_style_section_empty_for_professional(self) -> None:
        out = _build_language_style_section(
            country="ar",
            formality_level=0.2,
            active_mode="professional",
        )
        assert out == ""

    def test_language_style_section_empty_for_dating_nascent(self) -> None:
        out = _build_language_style_section(
            country="ar",
            formality_level=0.2,
            active_mode="dating",
            mode_message_count=10,
        )
        assert out == ""

    def test_language_style_section_renders_for_dating_warming(self) -> None:
        out = _build_language_style_section(
            country="ar",
            formality_level=0.2,
            active_mode="dating",
            mode_message_count=50,
        )
        assert "ADAPTACIÓN LINGÜÍSTICA" in out

    def test_language_style_section_renders_for_friends(self) -> None:
        out = _build_language_style_section(
            country="ar",
            formality_level=0.2,
            active_mode="friends",
        )
        assert "ADAPTACIÓN LINGÜÍSTICA" in out

    def test_behavior_tone_suppressed_for_professional(self) -> None:
        out = _build_behavior_section(
            {
                "tone_humor": 0.9,
                "tone_formality": 0.1,
                "tone_verbosity": 0.9,
                "preferred_topics": ["futbol"],
                "restricted_topics": ["politica"],
                "language": "es",
            },
            active_mode="professional",
        )
        assert "humor y bromas" not in out
        assert "Muy casual" not in out
        assert "detallado y extenso" not in out
        assert "Temas que le interesan" not in out
        # Policy / safety stays.
        assert "NO toques estos temas: politica" in out
        assert "Responde en español" in out

    def test_behavior_tone_suppressed_for_dating_nascent(self) -> None:
        out = _build_behavior_section(
            {"tone_humor": 0.9, "restricted_topics": ["sex"]},
            active_mode="dating",
            mode_message_count=5,
        )
        assert "humor y bromas" not in out
        assert "NO toques estos temas: sex" in out

    def test_behavior_tone_passes_through_for_friends(self) -> None:
        out = _build_behavior_section(
            {"tone_humor": 0.9, "tone_formality": 0.1},
            active_mode="friends",
        )
        assert "humor y bromas" in out
        assert "Muy casual" in out

    def test_full_prompt_strips_dialect_for_professional_argentine(self) -> None:
        # Sanity check: build the full prompt for an Argentine user in
        # professional mode and assert no voseo / regional markers leak in.
        out = build_avatar_system_prompt(
            avatar_name="Avatar",
            display_name="Augusto",
            country="ar",
            formality_level=0.2,
            behavior_settings={"tone_humor": 0.9, "tone_formality": 0.1},
            active_mode="professional",
        )
        assert "ADAPTACIÓN LINGÜÍSTICA" not in out
        assert "Pronombre: vos" not in out
        assert "humor y bromas" not in out
        # Mode block still anchors the prompt.
        assert "MODO ACTIVO: PROFESIONAL" in out
