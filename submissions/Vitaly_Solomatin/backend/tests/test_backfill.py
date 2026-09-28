import io
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.backfill import FIRST_QUARTER, main, parse_args, parse_quarter, quarter_range, run_backfill
from app.dam_source.models import FetchError, Quarter
from app.dam_source.source import OreeDamSource
from app.storage.models import DamDay, DamPrice, DamRawSnapshot
from app.storage.repository import DamRepository
from tests.fakes import FakeDamSource, csv_bytes

Q = Quarter


def day_rows(day: str, price: str = "100.00", periods: int = 24) -> list[str]:
    return [f"{day};{p};{price};1.0;1.0;1.0;1.0" for p in range(1, periods + 1)]


def quarter_file(q: Quarter, price: str = "100.00") -> bytes:
    """Синтетичний квартал: дві доби по 24 періоди, дати з першого місяця кварталу."""
    month = (q.quarter - 1) * 3 + 1
    return csv_bytes(*day_rows(f"01.{month:02}.{q.year}", price), *day_rows(f"02.{month:02}.{q.year}", price))


class FailingSource(FakeDamSource):
    def __init__(self, files, fail_on: Quarter, error: BaseException):
        super().__init__(files)
        self.fail_on, self.error = fail_on, error

    async def fetch_raw(self, quarter):
        if quarter == self.fail_on:
            self.calls.append(quarter)
            raise self.error
        return await super().fetch_raw(quarter)


class SnapshotFailsRepository(DamRepository):
    """Зриває запис знімка вже ПІСЛЯ вставки записів у тій самій транзакції."""

    def __init__(self, sessions, fail_on: Quarter):
        super().__init__(sessions)
        self.fail_on = fail_on

    async def _insert_snapshot(self, session, year, quarter, content_hash, raw):
        if Quarter(year, quarter) == self.fail_on:
            raise RuntimeError("збій на півдорозі")
        await super()._insert_snapshot(session, year, quarter, content_hash, raw)


async def count(sessions, model, where=None) -> int:
    async with sessions() as s:
        stmt = select(func.count()).select_from(model)
        if where is not None:
            stmt = stmt.where(where)
        return (await s.execute(stmt)).scalar_one()


async def quarter_rows(sessions, q: Quarter) -> int:
    first = date(q.year, (q.quarter - 1) * 3 + 1, 1)
    last = date(q.next().year, (q.next().quarter - 1) * 3 + 1, 1)
    return await count(sessions, DamPrice, (DamPrice.delivery_date >= first) & (DamPrice.delivery_date < last))


async def backfill(source, repository, quarters, **kw):
    out = io.StringIO()
    report = await run_backfill(source, repository, quarters, delay=0, out=out, **kw)
    return report, out.getvalue()


# 1. Діапазон кварталів

def test_quarter_iteration_crosses_year():
    assert Q(2026, 4).next() == Q(2027, 1)
    assert quarter_range(Q(2025, 1), Q(2026, 2)) == [
        Q(2025, 1), Q(2025, 2), Q(2025, 3), Q(2025, 4), Q(2026, 1), Q(2026, 2)
    ]


def test_parse_quarter():
    assert parse_quarter("2025Q1") == Q(2025, 1)
    for bad in ["2025Q5", "20251", "2025-Q1", ""]:
        with pytest.raises(ValueError):
            parse_quarter(bad)


def test_default_range_is_first_quarter_to_current():
    quarters, _ = parse_args([], today=date(2026, 8, 15))
    assert quarters[0] == FIRST_QUARTER == Q(2019, 3)
    assert quarters[-1] == Q(2026, 3)


async def test_inverted_range_rejected_before_any_network(monkeypatch):
    async def no_network(self, quarter):
        raise AssertionError("звернення до джерела")

    monkeypatch.setattr(OreeDamSource, "fetch_raw", no_network)
    with pytest.raises(SystemExit) as exc:
        await main(["--from", "2025Q4", "--to", "2025Q1"])
    assert exc.value.code == 2


async def test_single_quarter_range(repository):
    source = FakeDamSource()
    await backfill(source, repository, quarter_range(Q(2025, 2), Q(2025, 2)))
    assert source.calls == [Q(2025, 2)]


# 2. Основний цикл

async def test_saves_all_quarters_in_chronological_order(repository, sessions, fixture_bytes):
    source = FakeDamSource({Q(2025, 1): fixture_bytes("dam_2025_Q1.csv"), Q(2025, 2): quarter_file(Q(2025, 2))})
    await backfill(source, repository, quarter_range(Q(2025, 1), Q(2025, 2)))
    assert source.calls == [Q(2025, 1), Q(2025, 2)]
    assert await quarter_rows(sessions, Q(2025, 1)) == 89 * 24 + 23
    assert await quarter_rows(sessions, Q(2025, 2)) == 48


async def test_failed_quarter_save_leaves_no_partial_data(sessions):
    files = {q: quarter_file(q) for q in quarter_range(Q(2025, 1), Q(2025, 3))}
    repository = SnapshotFailsRepository(sessions, fail_on=Q(2025, 3))
    report, _ = await backfill(FakeDamSource(files), repository, list(files))
    assert await quarter_rows(sessions, Q(2025, 1)) == 48
    assert await quarter_rows(sessions, Q(2025, 2)) == 48
    assert await quarter_rows(sessions, Q(2025, 3)) == 0
    assert await count(sessions, DamDay, DamDay.delivery_date >= date(2025, 7, 1)) == 0
    assert [q for q, _ in report.failed] == [Q(2025, 3)]


async def test_snapshot_and_day_hashes_per_quarter(repository, sessions):
    files = {q: quarter_file(q) for q in quarter_range(Q(2025, 1), Q(2025, 3))}
    await backfill(FakeDamSource(files), repository, list(files))
    assert await count(sessions, DamRawSnapshot) == 3
    assert await count(sessions, DamDay) == 6
    days = {r.delivery_date for r in await repository.get_records(date(2025, 1, 1), date(2025, 9, 30))}
    assert set(await repository.get_day_hashes(date(2025, 1, 1), date(2025, 9, 30))) == days


async def test_empty_quarter_is_neither_error_nor_snapshot(repository, sessions):
    source = FakeDamSource({Q(2019, 3): quarter_file(Q(2019, 3))})  # 2019Q2 -> лише заголовок
    report, _ = await backfill(source, repository, [Q(2019, 2), Q(2019, 3)])
    assert report.empty == [Q(2019, 2)]
    assert report.failed == []
    assert await count(sessions, DamRawSnapshot) == 1
    assert await quarter_rows(sessions, Q(2019, 3)) == 48


# 3. Ідемпотентність

async def test_rerun_same_range_changes_nothing(repository, sessions):
    files = {q: quarter_file(q) for q in quarter_range(Q(2025, 1), Q(2025, 2))}
    await backfill(FakeDamSource(files), repository, list(files))
    before = await repository.get_records(date(2025, 1, 1), date(2025, 6, 30))
    await backfill(FakeDamSource(files), repository, list(files))
    assert await repository.get_records(date(2025, 1, 1), date(2025, 6, 30)) == before
    assert await count(sessions, DamPrice) == 96


async def test_overlapping_ranges_do_not_duplicate(repository, sessions):
    files = {q: quarter_file(q) for q in quarter_range(Q(2025, 1), Q(2025, 3))}
    await backfill(FakeDamSource(files), repository, [Q(2025, 1), Q(2025, 2)])
    await backfill(FakeDamSource(files), repository, [Q(2025, 2), Q(2025, 3)])
    assert await quarter_rows(sessions, Q(2025, 2)) == 48
    assert await quarter_rows(sessions, Q(2025, 3)) == 48
    assert await count(sessions, DamPrice) == 144


async def test_rerun_picks_up_recalculated_values(repository, sessions):
    await backfill(FakeDamSource({Q(2025, 1): quarter_file(Q(2025, 1))}), repository, [Q(2025, 1)])
    await backfill(FakeDamSource({Q(2025, 1): quarter_file(Q(2025, 1), "250.50")}), repository, [Q(2025, 1)])
    records = await repository.get_records(date(2025, 1, 1), date(2025, 3, 31))
    assert {r.price for r in records} == {Decimal("250.50")}
    assert len(records) == 48


async def test_rerun_does_not_duplicate_snapshots(repository, sessions):
    files = {q: quarter_file(q) for q in quarter_range(Q(2025, 1), Q(2025, 2))}
    await backfill(FakeDamSource(files), repository, list(files))
    await backfill(FakeDamSource(files), repository, list(files))
    assert await count(sessions, DamRawSnapshot) == 2


# 4. Відновлюваність і стійкість

async def test_unavailable_quarter_does_not_stop_the_rest(repository, sessions):
    files = {q: quarter_file(q) for q in quarter_range(Q(2025, 1), Q(2025, 3))}
    source = FailingSource(files, fail_on=Q(2025, 2), error=FetchError("таймаут"))
    report, out = await backfill(source, repository, list(files))
    assert await quarter_rows(sessions, Q(2025, 1)) == 48
    assert await quarter_rows(sessions, Q(2025, 3)) == 48
    assert [q for q, _ in report.failed] == [Q(2025, 2)]
    assert report.exit_code == 1


async def test_exit_code_zero_when_all_succeed(repository):
    files = {q: quarter_file(q) for q in quarter_range(Q(2025, 1), Q(2025, 2))}
    report, _ = await backfill(FakeDamSource(files), repository, list(files))
    assert report.failed == [] and report.exit_code == 0


async def test_interrupted_run_resumes_on_rerun(repository, sessions):
    files = {q: quarter_file(q) for q in quarter_range(Q(2025, 1), Q(2025, 4))}
    interrupted = FailingSource(files, fail_on=Q(2025, 3), error=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        await backfill(interrupted, repository, list(files))
    assert await count(sessions, DamPrice) == 96  # два квартали цілі
    report, _ = await backfill(FakeDamSource(files), repository, list(files))
    assert report.exit_code == 0
    for q in files:
        assert await quarter_rows(sessions, q) == 48


async def test_broken_row_fails_quarter_without_partial_save(repository, sessions):
    broken = csv_bytes(*day_rows("01.04.2025"), "02.04.2025;1;abc;1.0;1.0;1.0;1.0")
    files = {Q(2025, 1): quarter_file(Q(2025, 1)), Q(2025, 2): broken, Q(2025, 3): quarter_file(Q(2025, 3))}
    report, _ = await backfill(FakeDamSource(files), repository, list(files))
    assert await quarter_rows(sessions, Q(2025, 2)) == 0
    assert [q for q, _ in report.failed] == [Q(2025, 2)]
    assert await quarter_rows(sessions, Q(2025, 3)) == 48


async def test_no_own_retries_on_top_of_source(repository):
    source = FailingSource({}, fail_on=Q(2025, 1), error=FetchError("недоступно"))
    await backfill(source, repository, [Q(2025, 1)])
    assert source.calls == [Q(2025, 1)]


# 5. Темп

async def test_pause_between_quarters_not_before_first(repository):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    await run_backfill(FakeDamSource(), repository, quarter_range(Q(2025, 1), Q(2025, 3)),
                       delay=1.5, sleep=fake_sleep, out=io.StringIO())
    assert sleeps == [1.5, 1.5]


async def test_zero_delay_disables_pauses(repository):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    await run_backfill(FakeDamSource(), repository, quarter_range(Q(2025, 1), Q(2025, 3)),
                       delay=0, sleep=fake_sleep, out=io.StringIO())
    assert sleeps == []


# 6. Вивід

async def test_progress_line_per_quarter(repository, fixture_bytes):
    source = FakeDamSource({Q(2025, 1): fixture_bytes("dam_2025_Q1.csv"), Q(2025, 2): quarter_file(Q(2025, 2))})
    _, out = await backfill(source, repository, [Q(2025, 1), Q(2025, 2)])
    assert "2025Q1  ... 90 діб, 2159 рядків" in out
    assert "2025Q2  ... 2 доби, 48 рядків" in out
    assert out.rstrip().splitlines()[-1].startswith("  успішно 2")


async def test_summary_counts_and_failed_names(repository):
    files = {Q(2025, 1): quarter_file(Q(2025, 1)), Q(2025, 3): quarter_file(Q(2025, 3))}
    source = FailingSource(files, fail_on=Q(2025, 4), error=FetchError("таймаут"))
    report, out = await backfill(source, repository, quarter_range(Q(2025, 1), Q(2025, 4)))
    assert "2025Q2  ... порожній" in out
    assert Q(2025, 2) not in [q for q, _ in report.failed]
    assert "успішно 2, порожніх 1, невдалих 1 -> код виходу 1" in out
    assert "невдалі: 2025Q4" in out
