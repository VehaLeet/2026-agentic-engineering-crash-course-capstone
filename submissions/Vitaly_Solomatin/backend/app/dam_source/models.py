from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

MIN_PERIOD = 1
MAX_PERIOD = 25  # доба переходу на зимовий час


class DamSourceError(Exception):
    """Базова помилка джерела даних РДН."""


class InvalidQuarterError(DamSourceError, ValueError):
    """Некоректний номер кварталу; до мережі не доходить."""


class FetchError(DamSourceError):
    """Джерело недоступне після всіх спроб. Не плутати з порожнім кварталом."""


class ParseError(DamSourceError):
    def __init__(self, line: int, reason: str):
        super().__init__(f"рядок {line}: {reason}")
        self.line = line


@dataclass(frozen=True, slots=True)
class DamRecord:
    delivery_date: date
    period: int  # порядковий номер 1..25 як у джерелі, не година доби
    price: Decimal
    volume_sell: Decimal
    volume_buy: Decimal
    declared_volume_sell: Decimal
    declared_volume_buy: Decimal


@dataclass(frozen=True, order=True, slots=True)
class Quarter:
    year: int
    quarter: int

    def __post_init__(self) -> None:
        if not 1 <= self.quarter <= 4:
            raise InvalidQuarterError(f"квартал має бути 1..4, отримано {self.quarter}")

    @classmethod
    def of(cls, day: date) -> Quarter:
        return cls(day.year, (day.month - 1) // 3 + 1)

    def next(self) -> Quarter:
        if self.quarter == 4:
            return Quarter(self.year + 1, 1)
        return Quarter(self.year, self.quarter + 1)

    def __str__(self) -> str:
        return f"{self.year}Q{self.quarter}"


@dataclass(frozen=True, slots=True)
class QuarterFetch:
    quarter: Quarter
    content_hash: str
    raw: bytes
    records: tuple[DamRecord, ...]


@dataclass(frozen=True, slots=True)
class CollectResult:
    records: tuple[DamRecord, ...]
    day_hashes: dict[date, str]
    fetches: tuple[QuarterFetch, ...]

    @property
    def file_hashes(self) -> dict[Quarter, str]:
        return {f.quarter: f.content_hash for f in self.fetches}
