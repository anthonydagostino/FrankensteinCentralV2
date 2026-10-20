"""Calendar period math for benefits (America/New_York dates)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from .catalog import Benefit


@dataclass(frozen=True)
class Period:
    key: str
    start: date
    end: date  # inclusive

    @property
    def label(self) -> str:
        if "-M" in self.key:
            return self.start.strftime("%B %Y")
        if "-Q" in self.key:
            return f"{self.key.split('-')[1]}: {self.start.strftime('%b')} to {self.end.strftime('%b')} {self.start.year}"
        if "-H" in self.key:
            return f"{self.key.split('-')[1]}: {self.start.strftime('%b')} to {self.end.strftime('%b')} {self.start.year}"
        return str(self.start.year)

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end

    def days_left(self, today: date) -> int:
        return max(0, (self.end - today).days)

    def ended(self, today: date) -> bool:
        return today > self.end


def _month_end(y: int, m: int) -> date:
    return (date(y, m, 28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def period_for(kind: str, d: date) -> Period:
    y = d.year
    if kind == "monthly":
        return Period(f"{y}-M{d.month:02d}", date(y, d.month, 1), _month_end(y, d.month))
    if kind == "quarterly":
        q = (d.month - 1) // 3 + 1
        sm = 3 * (q - 1) + 1
        return Period(f"{y}-Q{q}", date(y, sm, 1), _month_end(y, sm + 2))
    if kind == "semiannual":
        h = 1 if d.month <= 6 else 2
        sm = 1 if h == 1 else 7
        return Period(f"{y}-H{h}", date(y, sm, 1), _month_end(y, sm + 5))
    # annual and multi_year use the calendar year as the bookkeeping unit
    return Period(str(y), date(y, 1, 1), date(y, 12, 31))


def periods_in_year(kind: str, year: int, active_from: date | None = None, active_until: date | None = None) -> list[Period]:
    """Every period of this kind in the calendar year that overlaps the active range."""
    if kind == "monthly":
        starts = [date(year, m, 1) for m in range(1, 13)]
    elif kind == "quarterly":
        starts = [date(year, m, 1) for m in (1, 4, 7, 10)]
    elif kind == "semiannual":
        starts = [date(year, m, 1) for m in (1, 7)]
    else:
        starts = [date(year, 1, 1)]
    out = []
    for s in starts:
        p = period_for(kind, s)
        if active_from and p.end < active_from:
            continue
        if active_until and p.start > active_until:
            continue
        out.append(p)
    return out


def current_period(benefit: Benefit, today: date) -> Period | None:
    """The period containing today, or None if the benefit is not active today."""
    if not benefit.is_active_on(today):
        return None
    return period_for(benefit.period, today)


def cap_for(benefit: Benefit, period: Period) -> Decimal:
    """Cap for a period, honoring period_caps overrides by month number or period key."""
    if period.key in benefit.period_caps:
        return benefit.period_caps[period.key]
    if benefit.period == "monthly":
        month_key = str(period.start.month)
        if month_key in benefit.period_caps:
            return benefit.period_caps[month_key]
        padded = f"{period.start.month:02d}"
        if padded in benefit.period_caps:
            return benefit.period_caps[padded]
    return benefit.cap


def next_eligible(last_used: date | None, period_years: float) -> date | None:
    if last_used is None:
        return None
    return last_used + timedelta(days=int(round(period_years * 365.25)))
