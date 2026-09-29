"""Налаштування розкладу збору в БД — одне джерело правди; розклад у пам'яті лише похідний."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.storage.models import COLLECT_INTERVAL_MAX, COLLECT_INTERVAL_MIN, AppSettings

SETTINGS_ROW_ID = 1


@dataclass(frozen=True, slots=True)
class ScheduleSettings:
    enabled: bool
    interval_minutes: int
    updated_at: datetime | None = None


class ScheduleSettingsStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def get(self) -> ScheduleSettings:
        async with self.sessions() as s, s.begin():
            # Самолікування: рядок із типовими значеннями, якщо його видалили (міграція створює його сама).
            await s.execute(insert(AppSettings).values(id=SETTINGS_ROW_ID).on_conflict_do_nothing())
            row = await s.get_one(AppSettings, SETTINGS_ROW_ID)
            return ScheduleSettings(row.schedule_enabled, row.collect_interval_minutes, row.updated_at)

    async def update(self, enabled: bool, interval_minutes: int) -> ScheduleSettings:
        if not COLLECT_INTERVAL_MIN <= interval_minutes <= COLLECT_INTERVAL_MAX:
            raise ValueError(
                f"інтервал {interval_minutes} хв поза межами {COLLECT_INTERVAL_MIN}…{COLLECT_INTERVAL_MAX}"
            )
        async with self.sessions() as s, s.begin():
            await s.execute(insert(AppSettings).values(id=SETTINGS_ROW_ID).on_conflict_do_nothing())
            await s.execute(
                update(AppSettings).where(AppSettings.id == SETTINGS_ROW_ID).values(
                    schedule_enabled=enabled, collect_interval_minutes=interval_minutes,
                    updated_at=func.clock_timestamp(),
                )
            )
            row = (await s.execute(
                select(AppSettings).where(AppSettings.id == SETTINGS_ROW_ID).execution_options(populate_existing=True)
            )).scalar_one()
            return ScheduleSettings(row.schedule_enabled, row.collect_interval_minutes, row.updated_at)


class NotificationSettingsStore:
    """Глобальний вимикач сповіщень у тому самому рядку app_settings."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def enabled(self) -> bool:
        async with self.sessions() as s, s.begin():
            await s.execute(insert(AppSettings).values(id=SETTINGS_ROW_ID).on_conflict_do_nothing())
            return (await s.execute(
                select(AppSettings.notifications_enabled).where(AppSettings.id == SETTINGS_ROW_ID)
            )).scalar_one()

    async def set_enabled(self, value: bool) -> bool:
        async with self.sessions() as s, s.begin():
            await s.execute(insert(AppSettings).values(id=SETTINGS_ROW_ID).on_conflict_do_nothing())
            await s.execute(
                update(AppSettings).where(AppSettings.id == SETTINGS_ROW_ID).values(
                    notifications_enabled=value, updated_at=func.clock_timestamp(),
                )
            )
        return value
