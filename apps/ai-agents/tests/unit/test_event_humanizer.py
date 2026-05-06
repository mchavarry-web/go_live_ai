"""Unit tests for the event humanizer.

Pure function — no LLM, no DB. Verifies relative-bucket selection and
Spanish phrasing across timezone boundaries.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.prompts.event_humanizer import humanize_event, serialize_events_for_prompt


# Reference "now": Tuesday 2026-05-05 17:00 UTC = 12:00 Lima (UTC-5).
_NOW_UTC = datetime(2026, 5, 5, 17, 0, tzinfo=UTC)
_LIMA = "America/Lima"


class TestHumanizeBuckets:
    """Each delta bucket renders the expected Spanish phrase."""

    def test_today_with_time(self) -> None:
        # 23:00 UTC = 18:00 Lima (same calendar day in Lima)
        out = humanize_event(
            occurs_at=datetime(2026, 5, 5, 23, 0, tzinfo=UTC),
            user_tz=_LIMA,
            has_time=True,
            now_utc=_NOW_UTC,
        )
        assert out == "hoy a las 18:00"

    def test_today_no_time(self) -> None:
        out = humanize_event(
            occurs_at=datetime(2026, 5, 5, 23, 0, tzinfo=UTC),
            user_tz=_LIMA,
            has_time=False,
            now_utc=_NOW_UTC,
        )
        assert out == "hoy"

    def test_tomorrow(self) -> None:
        # 14:00 UTC next day = 09:00 Lima
        out = humanize_event(
            occurs_at=datetime(2026, 5, 6, 14, 0, tzinfo=UTC),
            user_tz=_LIMA,
            has_time=True,
            now_utc=_NOW_UTC,
        )
        assert out == "mañana a las 09:00"

    def test_within_six_days_uses_weekday(self) -> None:
        # 2026-05-08 = Friday in Lima
        out = humanize_event(
            occurs_at=datetime(2026, 5, 8, 14, 0, tzinfo=UTC),
            user_tz=_LIMA,
            has_time=True,
            now_utc=_NOW_UTC,
        )
        assert out == "el viernes a las 09:00"

    def test_seven_to_thirteen_days_says_proximo(self) -> None:
        # Next Tuesday in Lima
        out = humanize_event(
            occurs_at=datetime(2026, 5, 12, 20, 0, tzinfo=UTC),
            user_tz=_LIMA,
            has_time=True,
            now_utc=_NOW_UTC,
        )
        assert out == "el próximo martes a las 15:00"

    def test_far_future_uses_date(self) -> None:
        out = humanize_event(
            occurs_at=datetime(2026, 7, 10, 14, 0, tzinfo=UTC),
            user_tz=_LIMA,
            has_time=False,
            now_utc=_NOW_UTC,
        )
        assert out == "el 10/07"

    def test_invalid_timezone_falls_back_to_iso(self) -> None:
        out = humanize_event(
            occurs_at=datetime(2026, 5, 6, 14, 0, tzinfo=UTC),
            user_tz="Not/A_RealZone",
            has_time=True,
            now_utc=_NOW_UTC,
        )
        # Should return the raw ISO timestamp rather than crash.
        assert "2026-05-06" in out


class TestSerializeForPrompt:
    """``serialize_events_for_prompt`` shapes ORM rows into prompt dicts."""

    def _row(self, *, title: str, occurs_at: datetime, has_time: bool = True):
        return SimpleNamespace(
            title=title,
            occurs_at=occurs_at,
            occurs_at_has_time=has_time,
        )

    def test_empty_input(self) -> None:
        assert serialize_events_for_prompt([], user_tz=_LIMA, now_utc=_NOW_UTC) == []
        assert serialize_events_for_prompt(None, user_tz=_LIMA, now_utc=_NOW_UTC) == []  # type: ignore[arg-type]

    def test_sort_order_and_keys(self) -> None:
        rows = [
            self._row(title="A", occurs_at=datetime(2026, 5, 12, 14, 0, tzinfo=UTC)),
            self._row(title="B", occurs_at=datetime(2026, 5, 6, 14, 0, tzinfo=UTC)),
        ]
        out = serialize_events_for_prompt(rows, user_tz=_LIMA, now_utc=_NOW_UTC)
        assert [e["title"] for e in out] == ["B", "A"], "events must sort by occurs_at"
        for entry in out:
            assert set(entry.keys()) == {"title", "when_human", "when_iso", "has_time"}
