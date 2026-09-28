"""Одноразовий бекфіл історії РДН за діапазон кварталів.

Ідемпотентний і відновлюваний: продовжити перерваний прогін — це запустити його знову.
Запуск: `uv run python -m app.backfill [--from 2019Q3] [--to 2026Q3] [--delay 2]`.
"""

import argparse
import asyncio
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import TextIO

from app.dam_source.models import Quarter
from app.dam_source.source import DamSource
from app.storage.repository import DamRepository

FIRST_QUARTER = Quarter(2019, 3)  # 01.07.2019 — запуск РДН; 2019Q2 порожній
DEFAULT_DELAY = 2.0

_QUARTER_RE = re.compile(r"^(\d{4})Q([1-4])$")


def parse_quarter(value: str) -> Quarter:
    match = _QUARTER_RE.match(value.strip().upper())
    if not match:
        raise ValueError(f"очікувався формат YYYYQN (напр. 2025Q1), отримано {value!r}")
    return Quarter(int(match[1]), int(match[2]))


def quarter_range(start: Quarter, end: Quarter) -> list[Quarter]:
    if start > end:
        raise ValueError(f"початок діапазону {start} пізніший за кінець {end}")
    quarters = [start]
    while quarters[-1] < end:
        quarters.append(quarters[-1].next())
    return quarters


@dataclass
class BackfillReport:
    saved: list[tuple[Quarter, int, int]] = field(default_factory=list)  # квартал, доби, рядки
    empty: list[Quarter] = field(default_factory=list)
    failed: list[tuple[Quarter, str]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if self.failed else 0


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


async def run_backfill(
    source: DamSource,
    repository: DamRepository,
    quarters: list[Quarter],
    delay: float = DEFAULT_DELAY,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    out: TextIO = sys.stdout,
) -> BackfillReport:
    report = BackfillReport()
    for index, quarter in enumerate(quarters):
        if index and delay > 0:
            await sleep(delay)
        try:
            # Власних ретраїв немає: вони вже в DamSource.
            fetch = await source.fetch_quarter(quarter.year, quarter.quarter)
            if not fetch.records:
                report.empty.append(quarter)
                print(f"  {quarter}  ... порожній", file=out, flush=True)
                continue
            await repository.save_quarter(fetch)
        except Exception as e:  # збій кварталу не зриває решту діапазону
            report.failed.append((quarter, str(e)))
            print(f"  {quarter}  ... ПОМИЛКА: {e}", file=out, flush=True)
            continue
        days = len({r.delivery_date for r in fetch.records})
        rows = len(fetch.records)
        report.saved.append((quarter, days, rows))
        print(
            f"  {quarter}  ... {_plural(days, 'доба', 'доби', 'діб')}, "
            f"{_plural(rows, 'рядок', 'рядки', 'рядків')}",
            file=out, flush=True,
        )

    print("  ----", file=out)
    print(
        f"  успішно {len(report.saved)}, порожніх {len(report.empty)}, "
        f"невдалих {len(report.failed)} -> код виходу {report.exit_code}",
        file=out,
    )
    if report.failed:
        print("  невдалі: " + ", ".join(str(q) for q, _ in report.failed), file=out)
    return report


def parse_args(argv: list[str] | None, today: date) -> tuple[list[Quarter], float]:
    parser = argparse.ArgumentParser(prog="backfill", description="Бекфіл історії РДН ОРЕЕ")
    parser.add_argument("--from", dest="start", default=str(FIRST_QUARTER), help="YYYYQN, типово 2019Q3")
    parser.add_argument("--to", dest="end", default=None, help="YYYYQN, типово поточний квартал")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="пауза між кварталами, с")
    args = parser.parse_args(argv)
    try:
        start = parse_quarter(args.start)
        end = parse_quarter(args.end) if args.end else Quarter.of(today)
        quarters = quarter_range(start, end)
    except ValueError as e:
        parser.error(str(e))
    if args.delay < 0:
        parser.error("--delay не може бути від'ємним")
    return quarters, args.delay


async def main(argv: list[str] | None = None, today: date | None = None) -> int:
    # Аргументи перевіряються до будь-якого з'єднання з ОРЕЕ чи БД.
    quarters, delay = parse_args(argv, today or date.today())

    from app.dam_source.source import OreeDamSource
    from app.storage.database import make_engine, make_session_factory

    engine = make_engine()
    try:
        report = await run_backfill(OreeDamSource(), DamRepository(make_session_factory(engine)), quarters, delay)
    finally:
        await engine.dispose()
    return report.exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
