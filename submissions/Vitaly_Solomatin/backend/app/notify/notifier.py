"""Розсилка сповіщення про запуск збору: журнал доставок гарантує «не більше одного»."""

import logging
import os
from collections.abc import Iterable
from datetime import date, datetime, timezone

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.notify.message import build_message
from app.notify.recipients import RecipientRepository
from app.notify.telegram import TelegramClient, TelegramError
from app.storage.models import NotificationDelivery
from app.storage.repository import DamRepository

log = logging.getLogger(__name__)


class Notifier:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        repository: DamRepository,
        client: TelegramClient | None,
    ):
        self.sessions = sessions
        self.repository = repository
        self.recipients = RecipientRepository(sessions)
        self.client = client  # None — токен не задано, сповіщення вимкнені

    async def notify_run(self, run_id: int, changed: Iterable[date], recalculated: Iterable[date] = ()) -> None:
        """Ніколи не кидає: результат запуску збору від доставки не залежить."""
        try:
            await self._notify(run_id, sorted(changed), list(recalculated))
        except Exception:
            log.exception("сповіщення для запуску #%s зірвалось", run_id)

    async def _notify(self, run_id: int, changed: list[date], recalculated: list[date]) -> None:
        if self.client is None or not changed:
            return
        chat_ids = await self.recipients.enabled()
        if not chat_ids:
            return
        daily = [d for d in await self.repository.get_daily(changed[0], changed[-1]) if d.delivery_date in set(changed)]
        text = build_message(daily, recalculated)
        for chat_id in chat_ids:
            if not await self._claim(run_id, chat_id):
                continue  # доставка вже є: ніколи не надсилаємо вдруге
            try:
                attempts = await self.client.send(chat_id, text)
                await self._finish(run_id, chat_id, "sent", attempts, None)
            except TelegramError as e:  # збій одного отримувача не зриває решту
                await self._finish(run_id, chat_id, "failed", self.client.attempts, str(e))

    async def _claim(self, run_id: int, chat_id: str) -> bool:
        """Записати pending ДО відправки. False, якщо доставка для пари вже існує."""
        async with self.sessions() as s, s.begin():
            result = await s.execute(
                insert(NotificationDelivery)
                .values(run_id=run_id, chat_id=chat_id, status="pending", created_at=datetime.now(timezone.utc))
                .on_conflict_do_nothing(constraint="uq_notification_deliveries_run_chat")
                .returning(NotificationDelivery.id)
            )
            return result.first() is not None

    async def _finish(self, run_id: int, chat_id: str, status: str, attempts: int, error: str | None) -> None:
        async with self.sessions() as s, s.begin():
            await s.execute(
                update(NotificationDelivery)
                .where(NotificationDelivery.run_id == run_id, NotificationDelivery.chat_id == chat_id)
                .values(status=status, attempts=attempts, error_message=error, finished_at=datetime.now(timezone.utc))
            )


def telegram_from_env() -> TelegramClient | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    return TelegramClient(token) if token else None


def notifier_from_env(sessions: async_sessionmaker[AsyncSession], repository: DamRepository) -> Notifier:
    client = telegram_from_env()
    if client is None:
        log.warning("TELEGRAM_BOT_TOKEN не задано — сповіщення вимкнені")
    return Notifier(sessions, repository, client)
