"""Benefit catalog: compiled patterns around the YAML models."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ...config_loader import BenefitConfig, BenefitsCatalog


@dataclass
class Benefit:
    id: str
    card: str
    name: str
    cap: Decimal
    period: str
    period_caps: dict[str, Decimal]
    period_years: float
    tracking: str
    enrollment_required: bool
    active_from: date | None
    active_until: date | None
    purchase_patterns: list[re.Pattern] = field(default_factory=list)
    purchase_exclude_patterns: list[re.Pattern] = field(default_factory=list)
    credit_patterns: list[re.Pattern] = field(default_factory=list)
    notes: str = ""

    def is_active_on(self, d: date) -> bool:
        if self.active_from and d < self.active_from:
            return False
        if self.active_until and d > self.active_until:
            return False
        return True

    def matches_merchant(self, text: str) -> bool:
        return any(p.search(text) for p in self.purchase_patterns)

    def matches_exclude(self, text: str) -> bool:
        return any(p.search(text) for p in self.purchase_exclude_patterns)

    def matches_credit(self, text: str) -> bool:
        return any(p.search(text) for p in self.credit_patterns)


def _compile(patterns: list[str]) -> list[re.Pattern]:
    out = []
    for p in patterns:
        try:
            out.append(re.compile(p, re.I))
        except re.error:
            out.append(re.compile(re.escape(p), re.I))
    return out


def from_config(cfg: BenefitConfig) -> Benefit:
    return Benefit(
        id=cfg.id,
        card=cfg.card,
        name=cfg.name,
        cap=Decimal(cfg.cap).quantize(Decimal("0.01")),
        period=cfg.period,
        period_caps={str(k): Decimal(v).quantize(Decimal("0.01")) for k, v in cfg.period_caps.items()},
        period_years=cfg.period_years,
        tracking=cfg.tracking,
        enrollment_required=cfg.enrollment_required,
        active_from=cfg.active_from,
        active_until=cfg.active_until,
        purchase_patterns=_compile(cfg.purchase_patterns),
        purchase_exclude_patterns=_compile(cfg.purchase_exclude_patterns),
        credit_patterns=_compile(cfg.credit_patterns),
        notes=cfg.notes,
    )


def load_catalog(catalog: BenefitsCatalog) -> list[Benefit]:
    return [from_config(b) for b in catalog.benefits]


def benefits_for_card(benefits: list[Benefit], card_id: str) -> list[Benefit]:
    return [b for b in benefits if b.card == card_id]
