"""Отримувачі сповіщень Telegram у БД (одне джерело правди для налаштувань)."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.storage.models import TelegramRecipient

_CHAT_ID = re.compile(r"^(-?\d+|@[A-Za-z][A-Za-z0-9_]{4,})$")


class InvalidChatId(ValueError):
    pass


def validate_chat_id(value: str) -> str:
    value = value.strip()
    if not _CHAT_ID.match(value):
        raise InvalidChatId(f"некоректний chat_id {value!r}: очікується ціле число або @channel")
    return value


@dataclass(frozen=True, slots=True)
class Recipient:
    chat_id: str
    enabled: bool


class RecipientRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def all(self) -> list[Recipient]:
        async with self.sessions() as s:
            rows = await s.execute(select(TelegramRecipient).order_by(TelegramRecipient.id))
            return [Recipient(r.chat_id, r.enabled) for r in rows.scalars()]

    async def enabled(self) -> list[str]:
        return [r.chat_id for r in await self.all() if r.enabled]

    async def add(self, chat_id: str) -> bool:
        """True, якщо додано; False, якщо такий отримувач уже є (без дубліката)."""
        chat_id = validate_chat_id(chat_id)
        async with self.sessions() as s, s.begin():
            result = await s.execute(
                insert(TelegramRecipient)
                .values(chat_id=chat_id, created_at=datetime.now(timezone.utc))
                .on_conflict_do_nothing(index_elements=[TelegramRecipient.chat_id])
                .returning(TelegramRecipient.id)
            )
            return result.first() is not None

    async def remove(self, chat_id: str) -> bool:
        async with self.sessions() as s, s.begin():
            result = await s.execute(delete(TelegramRecipient).where(TelegramRecipient.chat_id == chat_id.strip()))
            return result.rowcount > 0

    async def get(self, chat_id: str) -> Recipient | None:
        async with self.sessions() as s:
            row = (await s.execute(
                select(TelegramRecipient).where(TelegramRecipient.chat_id == chat_id.strip())
            )).scalar_one_or_none()
            return row and Recipient(row.chat_id, row.enabled)

    async def set_enabled(self, chat_id: str, enabled: bool) -> Recipient | None:
        async with self.sessions() as s, s.begin():
            row = (await s.execute(
                update(TelegramRecipient).where(TelegramRecipient.chat_id == chat_id.strip())
                .values(enabled=enabled).returning(TelegramRecipient.chat_id, TelegramRecipient.enabled)
            )).first()
            return row and Recipient(row.chat_id, row.enabled)
