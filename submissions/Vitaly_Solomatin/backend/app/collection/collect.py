"""Одна операція збору: джерело -> діф хешів діб -> сховище, зі слідом у журналі.

Запуск вручну: `uv run python -m app.collection.collect [--trigger manual|scheduled]`.
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncEngine

from app.collection.lock import dam_writer_lock
from app.collection.runs import RunLog
from app.dam_source.hashing import changed_days as diff_days
from app.dam_source.source import DamSource
from app.notify.notifier import Notifier
from app.storage.repository import DamRepository
from app.timeutil import kyiv_today


@dataclass(frozen=True, slots=True)
class CollectOutcome:
    run_id: int
    status: str
    changed_days: tuple[date, ...] = ()
    error: str | None = None


async def collect_once(
    source: DamSource,
    repository: DamRepository,
    runs: RunLog,
    engine: AsyncEngine,
    reference_date: date,
    trigger: str,
    run_id: int | None = None,
    notifier: Notifier | None = None,
) -> CollectOutcome:
    """`run_id` — рядок журналу, створений викликачем заздалегідь (HTTP віддає його до збору)."""
    async with dam_writer_lock(engine) as acquired:
        if run_id is None:
            run_id = await runs.start(trigger)  # на старті: загибель процесу лишить видимий слід
        if not acquired:
            # Не помилка і не «без змін»: інший записувач уже працює, чекати не будемо.
            await runs.finish(run_id, "skipped_locked")
            return CollectOutcome(run_id, "skipped_locked")

        try:
            result = await source.collect_for(reference_date)
            if not result.records:
                await runs.finish(run_id, "no_data")
                return CollectOutcome(run_id, "no_data")

            days = sorted(result.day_hashes)
            stored = await repository.get_day_hashes(days[0], days[-1])
            changed = diff_days(result.day_hashes, stored)
            if not changed:
                await runs.finish(run_id, "no_changes")
                return CollectOutcome(run_id, "no_changes")

            changed_set = set(changed)
            await repository.save_collected(  # лише змінені доби; записи, хеші і знімки — одна транзакція
                [r for r in result.records if r.delivery_date in changed_set],
                {d: result.day_hashes[d] for d in changed},
                result.fetches,
            )
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            await runs.finish(run_id, "error", error_message=error)
            return CollectOutcome(run_id, "error", error=error)

        await runs.finish(run_id, "success", changed)
        if notifier is not None:
            # Після фіксації success і всередині блокування: паралельний запуск не розішле ту саму зміну.
            recalculated = [d for d in changed if d in stored]
            await notifier.notify_run(run_id, changed, recalculated)
        return CollectOutcome(run_id, "success", tuple(changed))


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collect", description="Один збір результатів РДН ОРЕЕ")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="опорна дата, типово сьогодні")
    args = parser.parse_args(argv)

    from app.dam_source.source import OreeDamSource
    from app.storage.database import make_engine, make_session_factory

    from app.notify.notifier import notifier_from_env

    engine = make_engine()
    sessions = make_session_factory(engine)
    repository = DamRepository(sessions)
    try:
        outcome = await collect_once(
            OreeDamSource(), repository, RunLog(sessions), engine,
            args.date or kyiv_today(), args.trigger, notifier=notifier_from_env(sessions, repository),
        )
    finally:
        await engine.dispose()
    changed = ", ".join(d.isoformat() for d in outcome.changed_days) or "-"
    print(f"запуск #{outcome.run_id}: {outcome.status}; змінені доби: {changed}")
    if outcome.error:
        print(f"помилка: {outcome.error}")
    return 0 if outcome.status in ("success", "no_changes", "no_data") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
