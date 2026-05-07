"""Unit tests for the persona-evolution chain's prompt structure.

Wave A.4 (2026-05-06). Verifies that the anti-self-reinforcement rule
made it into the rendered prompt — the chain's actual behaviour against
the LLM is exercised in higher-level tests, but a deterministic check
on the prompt template guards against regressions when the file is
edited later.
"""

from app.chains.persona_evolution_chain import _PERSONA_EVOLUTION_TEMPLATE


def test_prompt_includes_anti_self_reinforcement_rule() -> None:
    assert "ANTI-AUTORREFUERZO" in _PERSONA_EVOLUTION_TEMPLATE
    # The core mental model — avatar phrases are NOT user-style evidence
    # unless the user reacts to them.
    assert "NO es evidencia" in _PERSONA_EVOLUTION_TEMPLATE
    assert "el usuario" in _PERSONA_EVOLUTION_TEMPLATE


def test_prompt_lists_user_reaction_signals() -> None:
    """The rule should enumerate what counts as user adoption of an avatar phrase."""
    assert "repite" in _PERSONA_EVOLUTION_TEMPLATE
    assert "confirma" in _PERSONA_EVOLUTION_TEMPLATE
    assert "contradice" in _PERSONA_EVOLUTION_TEMPLATE


def test_prompt_keeps_dialect_guardrail() -> None:
    """We didn't break the existing dialect-marker observation gate."""
    assert "[obs:" in _PERSONA_EVOLUTION_TEMPLATE
    assert "al menos 5 turnos" in _PERSONA_EVOLUTION_TEMPLATE
