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


async def test_send_does_not_retry_502():
    steps, sleeps = Steps((502, {}), (200, {"ok": True})), []
    with pytest.raises(TelegramError, match="HTTP 502") as e:
        await client(steps, sleeps).send("123", "x")
    assert len(steps.requests) == 1 and e.value.attempts == 1


@pytest.mark.parametrize("error", [httpx.ReadTimeout("timeout"), httpx.RemoteProtocolError("disconnected")])
async def test_send_does_not_retry_when_request_may_have_arrived(error):
    steps, sleeps = Steps(error, (200, {"ok": True})), []
    with pytest.raises(TelegramError) as e:
        await client(steps, sleeps).send("123", "x")
    assert len(steps.requests) == 1 and e.value.attempts == 1


async def test_send_retries_connect_error_then_ok():
    steps, sleeps = Steps(httpx.ConnectError("boom"), (200, {"ok": True})), []
    assert await client(steps, sleeps).send("123", "x") == 2


async def test_get_updates_retries_502_then_ok():
    steps, sleeps = Steps((502, {}), (200, {"ok": True, "result": []})), []
    assert await client(steps, sleeps).get_updates() == []
    assert len(steps.requests) == 2


async def test_429_waits_retry_after():
    steps, sleeps = Steps((429, {"ok": False, "parameters": {"retry_after": 3}}), (200, {"ok": True})), []
    await client(steps, sleeps).send("123", "x")
    assert sleeps == [3.0]


async def test_403_is_not_retried_and_keeps_description():
    steps, sleeps = Steps((403, {"ok": False, "description": "Forbidden: bot was blocked by the user"})), []
    with pytest.raises(TelegramError, match="blocked by the user") as e:
        await client(steps, sleeps).send("123", "x")
    assert len(steps.requests) == 1 and e.value.attempts == 1


async def test_persistent_network_failure_three_attempts():
    steps, sleeps = Steps(httpx.ConnectError("boom")), []
    with pytest.raises(TelegramError) as e:
        await client(steps, sleeps).send("123", "x")
    assert len(steps.requests) == 3 and e.value.attempts == 3


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
    days = [day(date(2026, 9, d), "1", "2", None if d == 10 else "1.5") for d in range(15, 0, -1)]
    text = build_message(days, recalculated=[date(2026, 9, d) for d in range(1, 16)])
    lines = text.splitlines()
    assert lines[2].startswith("06.09.2026")  # найпізніші 10 діб, за зростанням дати
    assert "05.09.2026" not in text
    assert "середньозважена — грн" in text  # null -> «—»
    assert f"…і ще {15 - MAX_DAYS} діб" in text
    assert len(text) <= TELEGRAM_LIMIT


def test_truncation_keeps_new_day():
    recalc = [date(2026, 9, d) for d in range(1, 13)]
    days = [day(d, "1", "2", "1.5") for d in recalc] + [day(date(2026, 9, 29), "1", "2", "1.5")]
    text = build_message(days, recalculated=recalc)
    shown = [line.split()[0] for line in text.splitlines() if line[:2].isdigit()]
    assert shown == [f"{d:02d}.09.2026" for d in range(4, 13)] + ["29.09.2026"]
    assert "03.09.2026" not in text and "…і ще 3 діб" in text


def test_truncation_many_new_days_keeps_latest():
    days = [day(date(2026, 9, d), "1", "2", "1.5") for d in range(1, 13)]
    text = build_message(days)
    shown = [line.split()[0] for line in text.splitlines() if line[:2].isdigit()]
    assert shown == [f"{d:02d}.09.2026" for d in range(3, 13)]
    assert "…і ще 2 діб" in text


async def test_recipient_enable_disable_and_get(sessions):
    from app.notify.recipients import Recipient, RecipientRepository
    repo = RecipientRepository(sessions)
    await repo.add("123456789")
    assert await repo.set_enabled("123456789", False) == Recipient("123456789", False)
    assert await repo.enabled() == []
    assert await repo.get("123456789") == Recipient("123456789", False)
    assert await repo.set_enabled("123456789", True) == Recipient("123456789", True)
    assert await repo.enabled() == ["123456789"]
    assert await repo.set_enabled("555", True) is None
    assert await repo.get("555") is None


# getUpdates

async def test_get_updates_reads_without_confirming_or_changing_bot_settings():
    import json as _json
    seen = []

    def handler(request):
        seen.append((request.url.path, _json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": [{"update_id": 1}]})

    client = TelegramClient("123:SECRET", transport=httpx.MockTransport(handler), sleep=_no_sleep)
    assert await client.get_updates() == [{"update_id": 1}]
    [(path, body)] = seen
    assert path == "/bot123:SECRET/getUpdates"
    assert "offset" not in body and "allowed_updates" not in body


async def test_get_updates_webhook_conflict_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(409, json={"ok": False, "description": "Conflict: can't use getUpdates method while webhook is active"})

    client = TelegramClient("123:SECRET", transport=httpx.MockTransport(handler), sleep=_no_sleep)
    with pytest.raises(TelegramError) as e:
        await client.get_updates()
    assert len(calls) == 1
    assert "webhook is active" in str(e.value) and "SECRET" not in str(e.value)


async def _no_sleep(_):
    pass
