"""Плановий збір: APScheduler у процесі API, розклад будується з налаштувань у БД.

Планувальник живе в пам'яті процесу, тож API мусить мати рівно один воркер (див. app/api/__main__.py).
Кілька воркерів не зламали б даних — advisory lock однаково не дасть писати одночасно, — але кожен
тікав би окремо й множив рядки `skipped_locked`.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.api.runs_manager import RunManager
from app.collection.runs import RunLog
from app.settings import ScheduleSettings

log = logging.getLogger(__name__)

JOB_ID = "collect"


def _trigger(interval_minutes: int) -> IntervalTrigger:
    # Явний UTC: без нього тригер APScheduler 3.x бере зону хоста (tzlocal), а не планувальника.
    return IntervalTrigger(minutes=interval_minutes, timezone=timezone.utc)


def collect_tick(runs: RunLog, manager: RunManager) -> Callable[[], Awaitable[None]]:
    """Один плановий тік: той самий збір, що й ручний, зі способом запуску `scheduled`."""

    async def tick() -> None:
        try:
            run_id = await runs.start("scheduled")
            # Чекаємо задачу: поки вона триває, max_instances=1 не пустить наступний тік.
            await manager.start(run_id, "scheduled")
        except Exception:
            # Збої всередині збору collect_once уже пише як `error`; тут — те, що сталось до чи навколо
            # нього (наприклад, БД недоступна на runs.start). Розклад має жити далі.
            log.exception("плановий збір не вдалося виконати")

    return tick


class CollectScheduler:
    def __init__(self, tick: Callable[[], Awaitable[None]]):
        self._tick = tick
        self._scheduler = AsyncIOScheduler(timezone=timezone.utc)

    def start(self, settings: ScheduleSettings) -> None:
        """Запустити планувальник; увімкнений розклад робить перший тік одразу."""
        self._scheduler.start()
        if settings.enabled:
            self._add(settings.interval_minutes, next_run_time=datetime.now(timezone.utc))

    def apply(self, settings: ScheduleSettings) -> None:
        """Застосувати нові налаштування без рестарту: наступний тік — через інтервал від цього моменту."""
        job = self._scheduler.get_job(JOB_ID)
        if not settings.enabled:
            if job is not None:
                self._scheduler.remove_job(JOB_ID)  # тік, що вже виконується, не переривається
        elif job is None:
            self._add(settings.interval_minutes)
        else:
            # Новий тригер рахує старт від «зараз»; resume_job рахував би від старого start_date.
            self._scheduler.reschedule_job(JOB_ID, trigger=_trigger(settings.interval_minutes))

    def next_run_at(self) -> datetime | None:
        job = self._scheduler.get_job(JOB_ID)
        return job.next_run_time if job is not None else None

    def shutdown(self) -> None:
        """Нових тіків не буде; тік, що виконується, скасовує RunManager.shutdown()."""
        if self._scheduler.running:
            self._scheduler.remove_all_jobs()
            self._scheduler.shutdown(wait=False)

    def _add(self, interval_minutes: int, **kwargs) -> None:
        self._scheduler.add_job(
            self._tick, _trigger(interval_minutes), id=JOB_ID, replace_existing=True,
            max_instances=1,  # тік пропускається, поки попередній плановий збір триває
            coalesce=True,  # прострочені тіки зливаються в один, а не наздоганяються пачкою
            misfire_grace_time=60,  # затримка event loop до хвилини не губить тік
            **kwargs,
        )
