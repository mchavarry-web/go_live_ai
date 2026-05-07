"""Phase 18 — dump a user's memory state as a markdown report.

Read-only, dev convenience. Writes a top-level summary plus per-substrate
sections (insights by category, upcoming events, latest summary, sample
transcript chunks). Pulls everything via the same repositories the
production code uses, so the report reflects exactly what the avatar sees.

Usage::

    .venv/bin/python -m scripts.dump_user_memory <user_id> [--output report.md]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import Settings
from app.repositories.audio_transcript_repository import AudioTranscriptRepository
from app.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from app.repositories.event_repository import EventRepository
from app.repositories.insight_repository import InsightRepository


async def _build_report(user_id: str) -> str:
    settings = Settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    lines: list[str] = []
    lines.append(f"# Memory snapshot — `{user_id}`")
    lines.append(f"_Generated {datetime.now(UTC).isoformat()}_\n")

    async with Session() as session:
        insight_repo = InsightRepository(session)
        event_repo = EventRepository(session)
        summary_repo = ConversationSummaryRepository(session)
        transcript_repo = AudioTranscriptRepository(session)

        total_insights = await insight_repo.count_by_user_id(user_id)
        by_category = await insight_repo.count_by_category(user_id)
        by_source = await insight_repo.count_by_source(user_id)
        recent_insights = await insight_repo.find_by_user_id(user_id, limit=10)

        upcoming = await event_repo.list_upcoming(
            user_id, now_utc=datetime.now(UTC), horizon_days=30, limit=20
        )
        all_events = await event_repo.find_by_user_id(user_id, limit=20)

        recent_summaries = await summary_repo.find_by_user_id(user_id, limit=5)
        recent_transcripts = await transcript_repo.find_by_user_id(user_id, limit=10)

    # ── Insights ──────────────────────────────────────────────────────
    lines.append("## Insights\n")
    lines.append(f"- Total: **{total_insights}**")
    if by_category:
        lines.append("- Per-category:")
        for cat, count in sorted(by_category.items(), key=lambda kv: -kv[1]):
            lines.append(f"  - `{cat}`: {count}")
    if by_source:
        lines.append("- Per-source:")
        for src, count in sorted(by_source.items(), key=lambda kv: -kv[1]):
            lines.append(f"  - `{src}`: {count}")
    if recent_insights:
        lines.append("\n### Most recent (10)\n")
        for ins in recent_insights:
            ts = ins.created_at.isoformat() if ins.created_at else "?"
            lines.append(
                f"- [{ts}] `{ins.category}` (conf {ins.confidence:.2f}, src `{ins.source}`) — {ins.content[:160]}"
            )

    # ── User events ───────────────────────────────────────────────────
    lines.append("\n## Events\n")
    lines.append(f"- Total rows: **{len(all_events)}** (showing last 20)")
    lines.append(f"- Active in next 30d: **{len(upcoming)}**")
    if upcoming:
        lines.append("\n### Upcoming\n")
        for ev in upcoming:
            lines.append(
                f"- [{ev.occurs_at.isoformat()}] {ev.title} _(src `{ev.source}`, status `{ev.status}`)_"
            )

    # ── Conversation summaries ────────────────────────────────────────
    lines.append("\n## Conversation summaries\n")
    if recent_summaries:
        lines.append(f"- Recent rows: **{len(recent_summaries)}**")
        for s in recent_summaries:
            superseded = "superseded" if s.superseded_at else "latest"
            lines.append(
                f"- [{s.created_at.isoformat()}] conv `{s.conversation_id}` ({superseded}, "
                f"{s.message_count} msgs, ~{s.summary_token_count}t): {s.summary[:200]}"
            )
    else:
        lines.append("- (none)")

    # ── Transcript chunks ─────────────────────────────────────────────
    lines.append("\n## Audio transcript chunks\n")
    if recent_transcripts:
        lines.append(f"- Recent rows: **{len(recent_transcripts)}**")
        for chunk in recent_transcripts:
            lines.append(
                f"- [{chunk.recorded_at.isoformat()}] session `{chunk.audio_session_id}` "
                f"seq {chunk.sequence_in_chunk}: {chunk.text[:160]}"
            )
    else:
        lines.append("- (none)")

    await engine.dispose()
    return "\n".join(lines) + "\n"


async def _amain(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump a user's memory as markdown.")
    parser.add_argument("user_id")
    parser.add_argument(
        "--output",
        default=None,
        help="Write report to this path. Default: stdout.",
    )
    args = parser.parse_args(argv)
    report = await _build_report(args.user_id)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Wrote {len(report)} chars to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv))


if __name__ == "__main__":
    raise SystemExit(main())
