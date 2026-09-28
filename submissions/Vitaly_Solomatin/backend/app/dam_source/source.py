import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from datetime import date, timedelta

import httpx

from app.dam_source.hashing import content_hash, day_hashes
from app.dam_source.models import CollectResult, FetchError, Quarter, QuarterFetch
from app.dam_source.parser import parse_csv

OREE_BASE_URL = "https://www.oree.com.ua"


class DamSource(ABC):
    @abstractmethod
    async def fetch_raw(self, quarter: Quarter) -> bytes:
        """Сирі байти квартального CSV."""

    async def fetch_quarter(self, year: int, quarter: int) -> QuarterFetch:
        q = Quarter(year, quarter)  # некоректний номер відсікається до мережі
        raw = await self.fetch_raw(q)
        return QuarterFetch(q, content_hash(raw), raw, tuple(parse_csv(raw)))

    async def collect_for(self, reference_date: date) -> CollectResult:
        # Публікація за добу до постачання: завтрашня доба може бути вже в наступному кварталі.
        quarters = sorted({Quarter.of(reference_date), Quarter.of(reference_date + timedelta(days=1))})
        fetches = tuple([await self.fetch_quarter(q.year, q.quarter) for q in quarters])
        records = tuple(r for f in fetches for r in f.records)
        return CollectResult(records, day_hashes(records), fetches)


class OreeDamSource(DamSource):
    def __init__(
        self,
        base_url: str = OREE_BASE_URL,
        timeout: float = 30.0,
        attempts: int = 3,
        backoff: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.attempts = attempts
        self.backoff = backoff
        self.transport = transport
        self.sleep = sleep

    def url_for(self, quarter: Quarter) -> str:
        return f"{self.base_url}/index.php/control/results_mo_stat_csv/DAM/{quarter.year}/{quarter.quarter}"

    async def fetch_raw(self, quarter: Quarter) -> bytes:
        url = self.url_for(quarter)
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            for attempt in range(self.attempts):
                if attempt:
                    await self.sleep(self.backoff * 2 ** (attempt - 1))
                try:
                    response = await client.get(url)
                except httpx.TransportError as e:  # включно з таймаутами
                    last_error = e
                    continue
                if response.status_code >= 500:
                    last_error = httpx.HTTPStatusError(
                        f"HTTP {response.status_code}", request=response.request, response=response
                    )
                    continue
                if response.status_code >= 400:
                    raise FetchError(f"{url}: HTTP {response.status_code}")
                return response.content
        raise FetchError(f"{url}: {self.attempts} спроби невдалі: {last_error}") from last_error
