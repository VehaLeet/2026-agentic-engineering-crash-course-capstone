"""Взаємне виключення записувачів результатів РДН: збір і бекфіл беруть один ключ."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# Один ключ на всіх записувачів РДН — саме це робить інваріант спільним.
DAM_WRITER_LOCK_KEY = 0x0DA3_0001


@asynccontextmanager
async def dam_writer_lock(engine: AsyncEngine) -> AsyncIterator[bool]:
    """Неблокувальна спроба: віддає True, якщо блокування взято, False — якщо його тримає інший.

    Блокування сесійне і тримається на окремому з'єднанні весь час блоку. Обрив з'єднання
    (загибель процесу) звільняє його на боці Postgres автоматично.
    """
    async with engine.connect() as conn:
        acquired = (
            await conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": DAM_WRITER_LOCK_KEY})
        ).scalar_one()
        await conn.commit()  # не тримати відкриту транзакцію разом із блокуванням
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": DAM_WRITER_LOCK_KEY})
                    await conn.commit()
                except BaseException:
                    # Не повертати в пул з'єднання, що досі може тримати блокування.
                    await conn.invalidate()
                    raise
