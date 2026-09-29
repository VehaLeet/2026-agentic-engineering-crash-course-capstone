"""Текст сповіщення — чиста функція від подобових даних змінених діб."""

from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal

from app.storage.repository import DailyPrices

MAX_DAYS = 10
TELEGRAM_LIMIT = 4096


def _num(value: Decimal | None) -> str:
    """uk-UA, як в UI: нерозривний пробіл між тисячами, кома, два знаки; None -> «—»."""
    if value is None:
        return "—"
    whole, frac = f"{value:,.2f}".split(".")
    return whole.replace(",", " ") + "," + frac


def _date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def build_message(daily: Sequence[DailyPrices], recalculated: Iterable[date] = ()) -> str:
    recalc = set(recalculated)
    days = sorted(daily, key=lambda x: x.delivery_date)
    lines = ["РДН: оновлено результати"]
    for d in days[:MAX_DAYS]:
        mark = " (перераховано)" if d.delivery_date in recalc else ""
        lines += [
            "",
            f"{_date(d.delivery_date)}{mark}",
            f"  мін {_num(d.price_min)} · макс {_num(d.price_max)} · "
            f"середньозважена {_num(d.price_weighted)} грн/МВт·год",
        ]
    if len(days) > MAX_DAYS:
        lines += ["", f"…і ще {len(days) - MAX_DAYS} діб"]
    return "\n".join(lines)[:TELEGRAM_LIMIT]


TEST_TEXT = "OREE DAM Monitor: тестове повідомлення. Сповіщення про нові результати РДН приходитимуть сюди."
