from collections import Counter
from datetime import date
from decimal import Decimal

import pytest

from app.dam_source.models import ParseError
from app.dam_source.parser import parse_csv
from tests.fakes import HEADER_ONLY, csv_bytes


def test_parses_real_row_exactly(fixture_bytes):
    records = parse_csv(fixture_bytes("dam_2026_Q3.csv"))
    first = records[0]
    assert first.delivery_date == date(2026, 7, 1)
    assert first.period == 1
    assert first.price == Decimal("14947.80")
    assert first.volume_sell == Decimal("3246.2")
    assert first.volume_buy == Decimal("3246.2")
    assert first.declared_volume_sell == Decimal("3944.4")
    assert first.declared_volume_buy == Decimal("3323.5")


def test_bom_does_not_leak_into_first_column(fixture_bytes):
    records = parse_csv(fixture_bytes("dam_2026_Q3.csv"))
    assert records[0].delivery_date == date(2026, 7, 1)
    assert all("﻿" not in r.delivery_date.isoformat() for r in records)


@pytest.mark.parametrize("price", ["0.00", "-150.25"])
def test_zero_and_negative_price(price):
    [r] = parse_csv(csv_bytes(f"01.07.2026;1;{price};1.0;1.0;1.0;1.0"))
    assert r.price == Decimal(price)


@pytest.mark.parametrize(
    "bad_row",
    ["01.07.2026;2;100.00;1.0;1.0", "01.07.2026;2;abc;1.0;1.0;1.0;1.0", "01.07.2026;2;NaN;1.0;1.0;1.0;1.0"],
    ids=["missing-fields", "non-numeric", "nan"],
)
def test_broken_row_reports_line_and_returns_nothing(bad_row):
    raw = csv_bytes("01.07.2026;1;100.00;1.0;1.0;1.0;1.0", bad_row)
    with pytest.raises(ParseError) as exc:
        parse_csv(raw)
    assert exc.value.line == 3
    assert "рядок 3" in str(exc.value)


def _periods(records, day):
    return [r.period for r in records if r.delivery_date == day]


def test_regular_day_has_24_periods(fixture_bytes):
    records = parse_csv(fixture_bytes("dam_2026_Q3.csv"))
    assert _periods(records, date(2026, 7, 1)) == list(range(1, 25))


def test_spring_dst_day_has_23_periods(fixture_bytes):
    records = parse_csv(fixture_bytes("dam_2025_Q1.csv"))
    assert _periods(records, date(2025, 3, 30)) == list(range(1, 24))


def test_autumn_dst_day_has_25_periods(fixture_bytes):
    records = parse_csv(fixture_bytes("dam_2025_Q4.csv"))
    assert _periods(records, date(2025, 10, 26)) == list(range(1, 26))
    per_day = Counter(Counter(r.delivery_date for r in records).values())
    assert per_day == {24: 91, 25: 1}


@pytest.mark.parametrize("period", ["0", "26"])
def test_period_out_of_range_is_parse_error(period):
    with pytest.raises(ParseError):
        parse_csv(csv_bytes(f"01.07.2026;{period};100.00;1.0;1.0;1.0;1.0"))


def test_header_only_file_is_empty_result():
    assert parse_csv(HEADER_ONLY) == []
