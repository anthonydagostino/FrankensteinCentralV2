"""Small shared helpers: time, money, JSON."""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
TWO_PLACES = Decimal("0.01")


def utcnow() -> datetime:
    return datetime.now(UTC)


def local_tz() -> ZoneInfo:
    """The display timezone from dashboard.yaml (America/New_York if it cannot be read)."""
    from .config_loader import get_dashboard_config

    try:
        return ZoneInfo(get_dashboard_config().timezone)
    except Exception:  # pragma: no cover - config validated at startup
        return NY


def local_now() -> datetime:
    return utcnow().astimezone(local_tz())


def today_local() -> date:
    return local_now().date()


def iso(dt: datetime | date | None) -> str | None:
    """ISO 8601 string for a date or datetime (naive datetimes are taken as UTC); None passes through."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat()
    return dt.isoformat()


def parse_iso(value: str | None) -> datetime | None:
    """Aware datetime from an ISO string ('Z' accepted); None when missing or invalid."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def money(value: Any) -> Decimal:
    """Parse any numeric looking input into a Decimal with two places."""
    if value is None or value == "":
        return Decimal("0.00")
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return d.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def money_str(value: Any) -> str:
    """Two decimal string for a money value; raises on malformed input."""
    return f"{money(value):.2f}"


class JSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return f"{o.quantize(TWO_PLACES, rounding=ROUND_HALF_UP):.2f}"
        if isinstance(o, (datetime, date)):
            return iso(o)
        if isinstance(o, set):
            return sorted(o)
        return super().default(o)


def dumps(data: Any) -> str:
    """Compact JSON with Decimal, date, and datetime support."""
    return json.dumps(data, cls=JSONEncoder, separators=(",", ":"))


def compile_pattern(pattern: str) -> re.Pattern:
    """Case insensitive regex from config; an invalid pattern falls back to a literal match instead of failing startup."""
    try:
        return re.compile(pattern, re.I)
    except re.error:
        return re.compile(re.escape(pattern), re.I)


def strip_html(text: str | None) -> str:
    """Plain text from a calendar description: <br> becomes a newline, other tags are dropped, entities decoded."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).replace("\xa0", " ").strip()
