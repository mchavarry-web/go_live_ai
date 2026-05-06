"""Humanize a future event timestamp into a Spanish-first phrase.

Used at profile-building time to convert ``UserEventModel.occurs_at``
into the natural-language fragment that ends up in the avatar's system
prompt. Pure function with no LLM dependency.

Examples (assuming user tz America/Lima, now=2026-05-05 12:00 local):

    occurs_at=2026-05-05 18:00 local, has_time=True  → "hoy a las 18:00"
    occurs_at=2026-05-06 09:00 local, has_time=True  → "mañana a las 09:00"
    occurs_at=2026-05-06 09:00 local, has_time=False → "mañana"
    occurs_at=2026-05-12 15:00 local, has_time=True  → "el martes a las 15:00"
    occurs_at=2026-05-19 15:00 local, has_time=True  → "el próximo martes a las 15:00"
    occurs_at=2026-06-15 15:00 local, has_time=True  → "el 15/06 a las 15:00"
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

_WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def humanize_event(
    *,
    occurs_at: datetime,
    user_tz: str,
    has_time: bool,
    now_utc: datetime,
    lang: str = "es",
) -> str:
    """Render an event timestamp as a natural-language Spanish phrase.

    Args:
        occurs_at: tz-aware UTC datetime of the event.
        user_tz: IANA tz name (e.g. ``"America/Lima"``). Invalid names
            fall back silently to printing the ISO date.
        has_time: When False, omit the clock component.
        now_utc: Current UTC timestamp; relative bucketing is computed
            against this.
        lang: Reserved for future English support. Currently only ``"es"``
            is implemented; any other value also returns Spanish.

    Returns:
        A short Spanish phrase suitable for a prompt bullet.
    """
    del lang  # currently always Spanish

    try:
        tz = ZoneInfo(user_tz)
    except Exception:
        return occurs_at.isoformat()

    occurs_local = occurs_at.astimezone(tz)
    now_local = now_utc.astimezone(tz)

    today_local = now_local.date()
    delta_days = (occurs_local.date() - today_local).days

    time_part = occurs_local.strftime("%H:%M")
    date_part = occurs_local.strftime("%d/%m")

    if delta_days == 0:
        return f"hoy a las {time_part}" if has_time else "hoy"
    if delta_days == 1:
        return f"mañana a las {time_part}" if has_time else "mañana"
    if 2 <= delta_days <= 6:
        weekday = _WEEKDAYS_ES[occurs_local.weekday()]
        return f"el {weekday} a las {time_part}" if has_time else f"el {weekday}"
    if 7 <= delta_days <= 13:
        weekday = _WEEKDAYS_ES[occurs_local.weekday()]
        return (
            f"el próximo {weekday} a las {time_part}"
            if has_time
            else f"el próximo {weekday}"
        )
    return f"el {date_part} a las {time_part}" if has_time else f"el {date_part}"


def serialize_events_for_prompt(
    events: list,
    *,
    user_tz: str,
    now_utc: datetime,
) -> list[dict[str, str | bool]]:
    """Serialize a list of ``UserEventModel`` rows into prompt-ready dicts.

    Returns a list of ``{title, when_human, when_iso, has_time}`` dicts,
    sorted by occurrence (the repository already returns them sorted, but
    we don't depend on it).

    Args:
        events: List of ``UserEventModel`` instances.
        user_tz: IANA tz name to render times in.
        now_utc: Current UTC timestamp for relative bucketing.

    Returns:
        List of dicts. Empty list if ``events`` is empty or None.
    """
    if not events:
        return []

    rendered: list[dict[str, str | bool]] = []
    sorted_events = sorted(events, key=lambda e: e.occurs_at)
    for ev in sorted_events:
        rendered.append(
            {
                "title": ev.title,
                "when_human": humanize_event(
                    occurs_at=ev.occurs_at,
                    user_tz=user_tz,
                    has_time=bool(ev.occurs_at_has_time),
                    now_utc=now_utc,
                ),
                "when_iso": ev.occurs_at.isoformat(),
                "has_time": bool(ev.occurs_at_has_time),
            }
        )
    return rendered
