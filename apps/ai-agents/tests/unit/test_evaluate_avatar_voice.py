"""Wave B.5 — wraps the eval harness as a pytest so regressions surface in CI."""

from scripts.evaluate_avatar_voice import SCENARIOS, check_sections


def test_eval_harness_section_check_passes() -> None:
    """Every fixture in the eval harness must pass the deterministic section check."""
    assert check_sections() == 0


def test_at_least_six_scenarios_present() -> None:
    """Loose floor — keeps the harness from silently shrinking to nothing."""
    assert len(SCENARIOS) >= 6
