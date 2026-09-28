"""Schema shared by the repository and Alembic metadata checks."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CHAR, CheckConstraint, Date, DateTime, Identity, LargeBinary, Numeric, SmallInteger
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DamPrice(Base):
    __tablename__ = "dam_prices"
    __table_args__ = (CheckConstraint("period BETWEEN 1 AND 25", name="ck_dam_prices_period"),)

    delivery_date: Mapped[date] = mapped_column(Date, primary_key=True)
    period: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    volume_sell: Mapped[Decimal] = mapped_column(Numeric(12, 1), nullable=False)
    volume_buy: Mapped[Decimal] = mapped_column(Numeric(12, 1), nullable=False)
    declared_volume_sell: Mapped[Decimal] = mapped_column(Numeric(12, 1), nullable=False)
    declared_volume_buy: Mapped[Decimal] = mapped_column(Numeric(12, 1), nullable=False)


class DamDay(Base):
    __tablename__ = "dam_days"

    delivery_date: Mapped[date] = mapped_column(Date, primary_key=True)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DamRawSnapshot(Base):
    __tablename__ = "dam_raw_snapshots"
    __table_args__ = (CheckConstraint("quarter BETWEEN 1 AND 4", name="ck_dam_raw_snapshots_quarter"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    quarter: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    raw_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
