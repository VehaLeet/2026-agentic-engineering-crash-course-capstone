from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.dam_source.hashing import day_hashes
from app.dam_source.parser import parse_csv
from app.notify.message import MAX_DAYS, TELEGRAM_LIMIT, build_message
from app.notify.recipients import InvalidChatId, RecipientRepository, validate_chat_id
from app.notify.telegram import TelegramClient, TelegramError
from app.storage.repository import DailyPrices

TOKEN = "123456:SECRET-token_value"


# 2. Отримувачі

@pytest.mark.parametrize("ok", ["123456789", "-1001234567890", "@oree_dam"])
def test_valid_chat_ids(ok):
    assert validate_chat_id(ok) == ok


@pytest.mark.parametrize("bad", ["hello world", "@ab", "12a", ""])
def test_invalid_chat_ids(bad):
    with pytest.raises(InvalidChatId):
        validate_chat_id(bad)


async def test_recipients_add_list_remove_no_duplicates(sessions):
    repo = RecipientRepository(sessions)
    assert await repo.add("123456789") is True
    assert await repo.add("-1001234567890") is True
    assert await repo.add("123456789") is False  # без дубліката
    assert [r.chat_id for r in await repo.all()] == ["123456789", "-1001234567890"]
    assert all(r.enabled for r in await repo.all())
    assert await repo.remove("123456789") is True
    assert await repo.enabled() == ["-1001234567890"]


async def test_disabled_recipients_are_not_targeted(sessions):
    from sqlalchemy import update
    from app.storage.models import TelegramRecipient
    repo = RecipientRepository(sessions)
    await repo.add("111")
    await repo.add("222")
    async with sessions() as s, s.begin():
        await s.execute(update(TelegramRecipient).where(TelegramRecipient.chat_id == "111").values(enabled=False))
    assert await repo.enabled() == ["222"]


# 3. Клієнт Bot API

class Steps:
    def __init__(self, *steps):
        self.steps, self.requests = list(steps), []

    def __call__(self, request):
        self.requests.append(request)
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if isinstance(step, Exception):
            raise step
        status, body = step
        return httpx.Response(status, json=body)


def client(steps: Steps, sleeps: list):
    async def sleep(s):
        sleeps.append(s)
    return TelegramClient(TOKEN, transport=httpx.MockTransport(steps), sleep=sleep)


async def test_send_request_shape():
    steps, sleeps = Steps((200, {"ok": True})), []
    assert await client(steps, sleeps).send("123", "привіт") == 1
    req = steps.requests[0]
    assert str(req.url) == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    import json
    assert json.loads(req.content) == {"chat_id": "123", "text": "привіт", "disable_web_page_preview": True}


async def test_retries_502_then_ok():
    steps, sleeps = Steps((502, {}), (200, {"ok": True})), []
    assert await client(steps, sleeps).send("123", "x") == 2


async def test_429_waits_retry_after():
    steps, sleeps = Steps((429, {"ok": False, "parameters": {"retry_after": 3}}), (200, {"ok": True})), []
    await client(steps, sleeps).send("123", "x")
    assert sleeps == [3.0]


async def test_403_is_not_retried_and_keeps_description():
    steps, sleeps = Steps((403, {"ok": False, "description": "Forbidden: bot was blocked by the user"})), []
    with pytest.raises(TelegramError, match="blocked by the user"):
        await client(steps, sleeps).send("123", "x")
    assert len(steps.requests) == 1


async def test_persistent_network_failure_three_attempts():
    steps, sleeps = Steps(httpx.ConnectError("boom")), []
    with pytest.raises(TelegramError):
        await client(steps, sleeps).send("123", "x")
    assert len(steps.requests) == 3


async def test_token_never_leaks_into_errors():
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    steps, sleeps = Steps(httpx.ConnectError(f"All connection attempts failed for {url}")), []
    with pytest.raises(TelegramError) as e:
        await client(steps, sleeps).send("123", "x")
    assert TOKEN not in str(e.value) and "***" in str(e.value)


# 4. Повідомлення

def day(d, lo, hi, w):
    return DailyPrices(d, Decimal(lo), Decimal(hi), Decimal("0"), None if w is None else Decimal(w),
                       Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), 24)


async def test_message_on_real_oree_numbers(repository, fixture_bytes):
    records = parse_csv(fixture_bytes("dam_2026_Q3.csv"))
    await repository.save_records(records, day_hashes(records))
    daily = await repository.get_daily(date(2026, 9, 26), date(2026, 9, 26))
    text = build_message(daily, recalculated=[date(2026, 9, 26)]).replace(" ", " ")
    assert "26.09.2026 (перераховано)" in text
    assert "мін 15,00" in text and "макс 14 968,90" in text and "середньозважена 6 560,60" in text


def test_message_edge_cases():
    days = [day(date(2026, 9, d), "1", "2", None if d == 5 else "1.5") for d in range(15, 0, -1)]
    text = build_message(days)
    lines = text.splitlines()
    assert lines[2].startswith("01.09.2026")  # за зростанням дати
    assert "середньозважена — грн" in text  # null -> «—»
    assert f"…і ще {15 - MAX_DAYS} діб" in text
    assert len(text) <= TELEGRAM_LIMIT
