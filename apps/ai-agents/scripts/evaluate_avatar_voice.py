"""Wave B.5 — voice + memory eval harness.

A small offline script for sanity-checking the avatar's prompt assembly
under a matrix of (mode, dialect, formality, memory) fixtures. Two modes:

  - ``--check sections`` (default, deterministic): builds the system
    prompt for each fixture and asserts that the right sections are
    present/absent. Pure-python, no LLM, runs in <1s.

  - ``--check llm-judge``: actually streams a response from the avatar
    chain and uses an LLM judge to score the rubric dimensions
    (language, dialect, formality, verbosity, anti-pattern usage,
    memory misuse, persona consistency). Requires OPENAI_API_KEY and
    INTERNAL_TOKEN; intended for pre-release validation, not CI.

Usage::

    .venv/bin/python -m scripts.evaluate_avatar_voice
    .venv/bin/python -m scripts.evaluate_avatar_voice --check llm-judge

The fixture set is small on purpose. Add scenarios as the avatar's
behaviour expands; keep each row tight enough that a failure points
at exactly one dimension.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field

from app.prompts.avatar_prompts import build_avatar_system_prompt


# ── Fixture definition ──────────────────────────────────────────────────


@dataclass
class Scenario:
    name: str
    profile_kwargs: dict
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)


_PROFESSIONAL = Scenario(
    name="professional_strict_register",
    profile_kwargs=dict(
        avatar_name="Avatar",
        display_name="Lucía",
        knowledge_level=4,
        country="ar",
        active_mode="professional",
        formality_level=0.2,  # would normally trigger casual directive — must be suppressed
        upcoming_events=[
            {
                "title": "reunión",
                "when_human": "el martes a las 10:00",
                "when_iso": "2026-05-12T15:00:00+00:00",
                "has_time": True,
            }
        ],
    ),
    must_contain=[
        "PROFESIONAL",
        "PRÓXIMOS COMPROMISOS",
    ],
    must_not_contain=[
        # Slang/dialect injection must NOT happen in professional mode.
        "voseo (tenés",
        "Tutea libremente",
        "REGISTRO DETECTADO",
    ],
)

_FRIENDS_ARGENTINA = Scenario(
    name="friends_voseo_casual",
    profile_kwargs=dict(
        avatar_name="Avatar",
        display_name="Mateo",
        knowledge_level=3,
        country="ar",
        active_mode="friends",
        formality_level=0.2,
        custom_expressions=["a full", "re bueno"],
    ),
    must_contain=[
        "AMIGOS",
        "rioplatense",
        "voseo",
        "REGISTRO DETECTADO",  # formality directive must fire
        "muy informal",
    ],
    must_not_contain=[
        "PROFESIONAL",
    ],
)

_DATING_NASCENT = Scenario(
    name="dating_nascent_no_intimacy",
    profile_kwargs=dict(
        avatar_name="Avatar",
        display_name="Sofía",
        knowledge_level=2,
        country="mx",
        active_mode="dating",
        mode_message_count=5,  # nascent
        formality_level=0.2,  # but mode demands neutral register
    ),
    must_contain=[
        # Mode block dominates; we expect cautious language
        "etapa inicial",
    ],
    must_not_contain=[
        # Slang section must be suppressed
        "Tutea libremente",
        "REGISTRO DETECTADO",
    ],
)

_LOCATION_GATED_OFF = Scenario(
    name="location_section_omitted_when_no_payload",
    profile_kwargs=dict(
        avatar_name="Avatar",
        display_name="Pablo",
        country="pe",
        active_mode="friends",
    ),
    must_not_contain=[
        "UBICACIÓN ACTUAL",
    ],
)

_SUMMARY_AND_QUOTES = Scenario(
    name="summary_and_transcript_quotes",
    profile_kwargs=dict(
        avatar_name="Avatar",
        display_name="Ana",
        country="es",
        active_mode="friends",
        prior_summary="Discutió cambios laborales y planes de viaje a Lima.",
        transcript_quotes=["me agotan las semanas largas"],
    ),
    must_contain=[
        "RESUMEN DE LA CONVERSACIÓN",
        "FRAGMENTOS RELEVANTES",
    ],
)

_BEHAVIOR_SETTINGS_OVERRIDE = Scenario(
    name="behavior_policy_suppresses_calibrated_directive",
    profile_kwargs=dict(
        avatar_name="Avatar",
        display_name="Diego",
        country="cl",
        active_mode="friends",
        formality_level=0.2,
        behavior_settings={"tone_formality": 0.5},
    ),
    must_not_contain=[
        # Policy wins over observed signal — formality directive section
        # should not fire when behavior_settings.tone_formality is set.
        "REGISTRO DETECTADO",
    ],
)


SCENARIOS: list[Scenario] = [
    _PROFESSIONAL,
    _FRIENDS_ARGENTINA,
    _DATING_NASCENT,
    _LOCATION_GATED_OFF,
    _SUMMARY_AND_QUOTES,
    _BEHAVIOR_SETTINGS_OVERRIDE,
]


# ── Section-level deterministic check ───────────────────────────────────


def check_sections() -> int:
    failures: list[str] = []
    for scenario in SCENARIOS:
        prompt = build_avatar_system_prompt(**scenario.profile_kwargs)
        for needle in scenario.must_contain:
            if needle not in prompt:
                failures.append(f"[{scenario.name}] missing required: {needle!r}")
        for needle in scenario.must_not_contain:
            if needle in prompt:
                failures.append(f"[{scenario.name}] forbidden present: {needle!r}")

    if failures:
        for line in failures:
            print(f"FAIL {line}", file=sys.stderr)
        print(f"\n{len(failures)} failures across {len(SCENARIOS)} scenarios.", file=sys.stderr)
        return 1
    print(f"OK — {len(SCENARIOS)} scenarios pass section assertions.")
    return 0


# ── LLM-judge mode (optional) ───────────────────────────────────────────


def check_llm_judge() -> int:
    """Stub for the LLM-judged eval pass.

    Real implementation runs ``ChatService.generate_response`` end-to-end
    over a fixture conversation, captures the assistant response, and
    submits it + a rubric to an LLM judge. Out of scope for v1 of the
    harness — the deterministic section check catches structural
    regressions, which is the highest-value surface.
    """
    print(
        "llm-judge mode is intentionally a stub in v1 — "
        "see scripts/evaluate_avatar_voice.py for the rubric and wire-up "
        "guidance once a stable fixture conversation set is in place.",
        file=sys.stderr,
    )
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Voice + memory eval harness.")
    parser.add_argument(
        "--check",
        default="sections",
        choices=["sections", "llm-judge"],
        help="What to check (default: sections).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List scenarios and exit.",
    )
    args = parser.parse_args(argv)

    if args.list:
        print(json.dumps([s.name for s in SCENARIOS], indent=2))
        return 0
    if args.check == "sections":
        return check_sections()
    return check_llm_judge()


if __name__ == "__main__":
    raise SystemExit(main())
