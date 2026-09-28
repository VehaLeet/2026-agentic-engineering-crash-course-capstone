"""Розбір квартального CSV ОРЕЕ: UTF-8 з BOM, CRLF, роздільник `;`, 7 колонок."""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.dam_source.models import MAX_PERIOD, MIN_PERIOD, DamRecord, ParseError

COLUMNS = 7


def parse_csv(raw: bytes) -> list[DamRecord]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ParseError(1, f"не UTF-8: {e}") from e

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=";")
    header = next(reader, None)
    if header is None:
        raise ParseError(1, "порожній файл без заголовка")
    if len(header) != COLUMNS or header[0] != "Дата":
        raise ParseError(1, f"неочікуваний заголовок: {header!r}")

    records = []
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        records.append(_parse_row(row, reader.line_num))
    return records


def _parse_row(row: list[str], line: int) -> DamRecord:
    if len(row) != COLUMNS:
        raise ParseError(line, f"очікувалось {COLUMNS} полів, отримано {len(row)}")
    try:
        delivery_date = datetime.strptime(row[0], "%d.%m.%Y").date()
    except ValueError as e:
        raise ParseError(line, f"некоректна дата {row[0]!r}") from e
    try:
        period = int(row[1])
    except ValueError as e:
        raise ParseError(line, f"некоректний період {row[1]!r}") from e
    if not MIN_PERIOD <= period <= MAX_PERIOD:
        raise ParseError(line, f"період {period} поза {MIN_PERIOD}..{MAX_PERIOD}")
    price, *volumes = (_decimal(value, line) for value in row[2:])
    return DamRecord(delivery_date, period, price, *volumes)


def _decimal(value: str, line: int) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation as e:
        raise ParseError(line, f"нечислове значення {value!r}") from e
    if not number.is_finite():
        raise ParseError(line, f"нечислове значення {value!r}")
    return number
