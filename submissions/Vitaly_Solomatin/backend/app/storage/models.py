"""Schema shared by the repository and Alembic metadata checks."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CHAR, CheckConstraint, Date, DateTime, ForeignKey, Identity, Index, Integer, LargeBinary,
    Numeric,
    SmallInteger, Text, UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
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


RUN_STATUSES = ("success", "no_changes", "no_data", "error", "skipped_locked")
RUN_TRIGGERS = ("scheduled", "manual")


class CollectionRun(Base):
    """Журнал запусків. Рядок створюється на старті: status/finished_at NULL, поки запуск триває."""

    __tablename__ = "collection_runs"
    __table_args__ = (
        CheckConstraint(
            "status IS NULL OR status IN ('success', 'no_changes', 'no_data', 'error', 'skipped_locked')",
            name="ck_collection_runs_status",
        ),
        CheckConstraint("trigger IN ('scheduled', 'manual')", name="ck_collection_runs_trigger"),
        Index("ix_collection_runs_started_at", text("started_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    changed_days: Mapped[list[date]] = mapped_column(
        ARRAY(Date), nullable=False, server_default=text("'{}'::date[]")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class TelegramRecipient(Base):
    """Отримувач сповіщень. Налаштування — у БД (бриф); керування: CLI, згодом API/UI."""

    __tablename__ = "telegram_recipients"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    chat_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # ціле (зокрема від'ємне) або @channel
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


COLLECT_INTERVAL_MIN = 5  # хвилин; частіше — зайве навантаження на ОРЕЕ
COLLECT_INTERVAL_MAX = 1440  # раз на добу
COLLECT_INTERVAL_DEFAULT = 60


class AppSettings(Base):
    """Налаштування сервісу: рівно один рядок (id = 1). Зріз 9 додасть сюди свої колонки."""

    __tablename__ = "app_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_app_settings_single_row"),
        CheckConstraint(
            f"collect_interval_minutes BETWEEN {COLLECT_INTERVAL_MIN} AND {COLLECT_INTERVAL_MAX}",
            name="ck_app_settings_collect_interval",
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    collect_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text(str(COLLECT_INTERVAL_DEFAULT))
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


DELIVERY_STATUSES = ("pending", "sent", "failed")


class NotificationDelivery(Base):
    """Доставка сповіщення про запуск одному отримувачу. UNIQUE(run_id, chat_id) — «не більше одного»."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("run_id", "chat_id", name="uq_notification_deliveries_run_chat"),
        CheckConstraint("status IN ('pending', 'sent', 'failed')", name="ck_notification_deliveries_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("collection_runs.id"), nullable=False)
    chat_id: Mapped[str] = mapped_column(Text, nullable=False)  # копія: видалення отримувача не губить історію
    status: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
