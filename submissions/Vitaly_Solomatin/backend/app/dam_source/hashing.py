"""Дворівневе хешування: сирий файл (ранній вихід) і кожна доба постачання (діф)."""

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date

from app.dam_source.models import DamRecord


def content_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_line(r: DamRecord) -> str:
    # Фіксовані знаки як у джерелі: ціна 2, обсяги 1. Не залежить від подання Decimal.
    return "|".join((
        r.delivery_date.isoformat(),
        str(r.period),
        f"{r.price:.2f}",
        f"{r.volume_sell:.1f}",
        f"{r.volume_buy:.1f}",
        f"{r.declared_volume_sell:.1f}",
        f"{r.declared_volume_buy:.1f}",
    ))


def day_hashes(records: Iterable[DamRecord]) -> dict[date, str]:
    by_day: dict[date, list[DamRecord]] = defaultdict(list)
    for r in records:
        by_day[r.delivery_date].append(r)
    return {
        day: hashlib.sha256(
            "\n".join(_canonical_line(r) for r in sorted(rows, key=lambda r: r.period)).encode()
        ).hexdigest()
        for day, rows in by_day.items()
    }


def changed_days(current: Mapping[date, str], previous: Mapping[date, str]) -> list[date]:
    return sorted(day for day, h in current.items() if previous.get(day) != h)
