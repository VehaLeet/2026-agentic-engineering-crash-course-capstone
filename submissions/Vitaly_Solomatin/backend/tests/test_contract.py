from collections import Counter
from datetime import date

import httpx

from app.dam_source.hashing import content_hash
from app.dam_source.models import Quarter
from app.dam_source.source import DamSource
from tests.fakes import FakeDamSource


async def test_fake_source_needs_no_network(fixture_bytes, monkeypatch):
    def no_network(*a, **kw):
        raise AssertionError("мережевий виклик у тесті")

    monkeypatch.setattr(httpx.AsyncClient, "get", no_network)
    source: DamSource = FakeDamSource({Quarter(2026, 3): fixture_bytes("dam_2026_Q3.csv")})
    result = await source.collect_for(date(2026, 7, 15))
    assert result.records


async def test_end_to_end_on_fixtures(fixture_bytes):
    q3, q4 = fixture_bytes("dam_2025_Q1.csv"), fixture_bytes("dam_2019_Q2.csv")
    source = FakeDamSource({Quarter(2025, 1): q3, Quarter(2025, 2): q4})
    result = await source.collect_for(date(2025, 3, 31))  # межа кварталу: Q1 + порожній Q2

    per_day = Counter(r.delivery_date for r in result.records)
    assert len(per_day) == 90
    assert per_day[date(2025, 3, 30)] == 23
    assert result.file_hashes == {Quarter(2025, 1): content_hash(q3), Quarter(2025, 2): content_hash(q4)}
    assert set(result.day_hashes) == set(per_day)
    assert all(len(h) == 64 for h in result.day_hashes.values())
