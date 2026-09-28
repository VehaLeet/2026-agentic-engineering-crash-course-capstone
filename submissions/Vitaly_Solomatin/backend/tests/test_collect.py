from datetime import date

from app.dam_source.models import Quarter
from tests.fakes import FakeDamSource, csv_bytes


def row(day: str, period: int = 1) -> str:
    return f"{day};{period};100.00;1.0;1.0;1.0;1.0"


async def test_mid_quarter_fetches_one_quarter():
    source = FakeDamSource()
    await source.collect_for(date(2026, 9, 28))
    assert source.calls == [Quarter(2026, 3)]


async def test_last_day_of_quarter_fetches_both():
    source = FakeDamSource({
        Quarter(2026, 3): csv_bytes(row("30.09.2026")),
        Quarter(2026, 4): csv_bytes(row("01.10.2026")),
    })
    result = await source.collect_for(date(2026, 9, 30))
    assert source.calls == [Quarter(2026, 3), Quarter(2026, 4)]
    assert date(2026, 10, 1) in {r.delivery_date for r in result.records}


async def test_year_boundary():
    source = FakeDamSource()
    await source.collect_for(date(2026, 12, 31))
    assert source.calls == [Quarter(2026, 4), Quarter(2027, 1)]


async def test_empty_next_quarter_does_not_break_collection():
    source = FakeDamSource({Quarter(2026, 4): csv_bytes(row("31.12.2026"))})
    result = await source.collect_for(date(2026, 12, 31))
    assert [r.delivery_date for r in result.records] == [date(2026, 12, 31)]
