"""Only SQL boundary for DAM storage operations."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dam_source.hashing import day_hashes as compute_day_hashes
from app.dam_source.models import DamRecord, QuarterFetch
from app.storage.models import DamDay, DamPrice, DamRawSnapshot


@dataclass(frozen=True, slots=True)
class DailyPrices:
    """Подобовий агрегат. Не DamDay — це ім'я зайняте моделлю таблиці хешів діб."""

    delivery_date: date
    price_min: Decimal
    price_max: Decimal
    price_avg: Decimal  # проста середня за періодами (індекс BASE)
    price_weighted: Decimal | None  # зважена за обсягом продажу (= «середньозважена» ОРЕЕ); None, якщо обсяг 0
    volume_sell: Decimal
    volume_buy: Decimal
    declared_volume_sell: Decimal
    declared_volume_buy: Decimal
    periods: int


class DamRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def save_records(self, records: Iterable[DamRecord], day_hashes: Mapping[date, str]) -> None:
        async with self.sessions() as session, session.begin():
            await self._upsert_records(session, list(records), day_hashes)

    async def save_raw_snapshot(self, year: int, quarter: int, content_hash: str, raw: bytes) -> None:
        async with self.sessions() as session, session.begin():
            await self._insert_snapshot(session, year, quarter, content_hash, raw)

    async def save_quarter(self, fetch: QuarterFetch) -> None:
        """Записи, хеші діб і сирий знімок кварталу — однією транзакцією: або все, або нічого."""
        await self.save_collected(fetch.records, compute_day_hashes(fetch.records), [fetch])

    async def save_collected(
        self, records: Iterable[DamRecord], day_hashes: Mapping[date, str], fetches: Iterable[QuarterFetch]
    ) -> None:
        """Записи з хешами діб, потім знімки непорожніх файлів — одна транзакція."""
        async with self.sessions() as session, session.begin():
            await self._upsert_records(session, list(records), day_hashes)
            for fetch in fetches:
                if fetch.records:
                    await self._insert_snapshot(
                        session, fetch.quarter.year, fetch.quarter.quarter, fetch.content_hash, fetch.raw
                    )

    async def _upsert_records(
        self, session: AsyncSession, records: list[DamRecord], day_hashes: Mapping[date, str]
    ) -> None:
        rows = [
            {
                "delivery_date": r.delivery_date,
                "period": r.period,
                "price": r.price,
                "volume_sell": r.volume_sell,
                "volume_buy": r.volume_buy,
                "declared_volume_sell": r.declared_volume_sell,
                "declared_volume_buy": r.declared_volume_buy,
            }
            for r in records
        ]
        if set(day_hashes) != {row["delivery_date"] for row in rows}:
            raise ValueError("day hashes must match record dates")
        if rows:
            statement = insert(DamPrice).values(rows)
            await session.execute(statement.on_conflict_do_update(
                index_elements=[DamPrice.delivery_date, DamPrice.period],
                set_={name: getattr(statement.excluded, name) for name in (
                    "price", "volume_sell", "volume_buy", "declared_volume_sell", "declared_volume_buy"
                )},
            ))
        if day_hashes:
            statement = insert(DamDay).values([
                {"delivery_date": day, "content_hash": hash_, "updated_at": datetime.now(timezone.utc)}
                for day, hash_ in day_hashes.items()
            ])
            await session.execute(statement.on_conflict_do_update(
                index_elements=[DamDay.delivery_date],
                set_={"content_hash": statement.excluded.content_hash,
                      "updated_at": statement.excluded.updated_at},
            ))

    async def _insert_snapshot(
        self, session: AsyncSession, year: int, quarter: int, content_hash: str, raw: bytes
    ) -> None:
        statement = insert(DamRawSnapshot).values(
            year=year, quarter=quarter, content_hash=content_hash,
            raw_content=raw, fetched_at=datetime.now(timezone.utc),
        )
        await session.execute(statement.on_conflict_do_nothing(index_elements=[DamRawSnapshot.content_hash]))

    async def get_records(self, date_from: date, date_to: date) -> list[DamRecord]:
        if date_from > date_to:
            raise ValueError("date_from must not be after date_to")
        async with self.sessions() as session:
            result = await session.execute(
                select(DamPrice).where(DamPrice.delivery_date.between(date_from, date_to))
                .order_by(DamPrice.delivery_date, DamPrice.period)
            )
            return [DamRecord(r.delivery_date, r.period, r.price, r.volume_sell, r.volume_buy,
                              r.declared_volume_sell, r.declared_volume_buy) for r in result.scalars()]

    async def get_day_hashes(self, date_from: date, date_to: date) -> dict[date, str]:
        if date_from > date_to:
            raise ValueError("date_from must not be after date_to")
        async with self.sessions() as session:
            result = await session.execute(
                select(DamDay.delivery_date, DamDay.content_hash)
                .where(DamDay.delivery_date.between(date_from, date_to))
                .order_by(DamDay.delivery_date)
            )
            return dict(result.all())

    async def get_daily(self, date_from: date, date_to: date) -> list[DailyPrices]:
        if date_from > date_to:
            raise ValueError("date_from must not be after date_to")
        p = DamPrice
        statement = (
            select(
                p.delivery_date,
                func.min(p.price), func.max(p.price),
                func.round(func.avg(p.price), 2),
                func.round(func.sum(p.price * p.volume_sell) / func.nullif(func.sum(p.volume_sell), 0), 2),
                func.sum(p.volume_sell), func.sum(p.volume_buy),
                func.sum(p.declared_volume_sell), func.sum(p.declared_volume_buy),
                func.count(),
            )
            .where(p.delivery_date.between(date_from, date_to))
            .group_by(p.delivery_date)
            .order_by(p.delivery_date)
        )
        async with self.sessions() as session:
            return [DailyPrices(*row) for row in await session.execute(statement)]
