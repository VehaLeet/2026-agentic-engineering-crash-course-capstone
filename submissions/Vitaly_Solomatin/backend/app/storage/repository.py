"""Only SQL boundary for DAM storage operations."""

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dam_source.models import DamRecord
from app.storage.models import DamDay, DamPrice, DamRawSnapshot


class DamRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def save_records(self, records: Iterable[DamRecord], day_hashes: Mapping[date, str]) -> None:
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
        async with self.sessions() as session, session.begin():
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

    async def save_raw_snapshot(self, year: int, quarter: int, content_hash: str, raw: bytes) -> None:
        async with self.sessions() as session, session.begin():
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
