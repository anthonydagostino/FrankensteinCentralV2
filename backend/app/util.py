"""Small shared helpers: time, money, JSON."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
TWO_PLACES = Decimal("0.01")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def local_tz() -> ZoneInfo:
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
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return dt.isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def money(value: Any) -> Decimal:
    """Parse any numeric looking input into a Decimal with two places."""
    if value is None or value == "":
        return Decimal("0.00")
    if isinstance(value, Decimal):
        d = value
    else:
        d = Decimal(str(value))
    return d.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def money_str(value: Any) -> str:
    return f"{money(value):.2f}"


class JSONEncoder(json.JSONEncoder):
    def default(self, o: Any):  # type: ignore[override]
        if isinstance(o, Decimal):
            return f"{o.quantize(TWO_PLACES, rounding=ROUND_HALF_UP):.2f}"
        if isinstance(o, (datetime, date)):
            return iso(o)
        if isinstance(o, set):
            return sorted(o)
        return super().default(o)


def dumps(data: Any) -> str:
    return json.dumps(data, cls=JSONEncoder, separators=(",", ":"))


def jsonable(data: Any) -> Any:
    """Round trip through JSON so Decimals become strings and dates become ISO text."""
    return json.loads(dumps(data))


_WS = re.compile(r"\s+")


def squash(text: str | None) -> str:
    return _WS.sub(" ", (text or "")).strip()


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()
