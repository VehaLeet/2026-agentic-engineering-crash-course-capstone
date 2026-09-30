import io
from datetime import date

import httpx
import pytest
from sqlalchemy import select

from app.backfill import run_locked_backfill
from app.collection.collect import collect_once
from app.collection.runs import RunLog
from app.notify.notifier import Notifier, notifier_from_env
from app.notify.recipients import RecipientRepository
from app.notify.telegram import TelegramClient
from app.storage.models import NotificationDelivery
from tests.fakes import FakeDamSource
from tests.test_collection import Q3, REF, DownSource, held_lock, q3_file  # noqa: F401

TOKEN = "123456:SECRET"


class FakeTelegram:
    """Підставний Bot API: записує (chat_id, text); окремим chat_id можна задати помилку."""

    def __init__(self, fail: dict[str, int] | None = None):
        self.fail, self.sent = fail or {}, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        import json
        body = json.loads(request.content)
        code = self.fail.get(body["chat_id"])
        if code:
            return httpx.Response(code, json={"ok": False, "description": "Forbidden: bot was blocked by the user"})
        self.sent.append((body["chat_id"], body["text"]))
        return httpx.Response(200, json={"ok": True})


async def no_sleep(_):
    pass


def make_notifier(sessions, repository, tg: FakeTelegram) -> Notifier:
    return Notifier(sessions, repository, TelegramClient(TOKEN, transport=httpx.MockTransport(tg), sleep=no_sleep))


async def deliveries(sessions):
    async with sessions() as s:
        return [(d.chat_id, d.status, d.attempts, d.error_message)
                for d in (await s.execute(select(NotificationDelivery).order_by(NotificationDelivery.chat_id))).scalars()]


@pytest.fixture
async def two_recipients(sessions):
    repo = RecipientRepository(sessions)
    await repo.add("111")
    await repo.add("222")


async def collect(source, repository, sessions, engine, notifier):
    return await collect_once(source, repository, RunLog(sessions), engine, REF, "manual", notifier=notifier)


async def test_success_notifies_every_recipient_once(repository, sessions, engine, two_recipients):
    tg = FakeTelegram()
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), repository, sessions, engine, make_notifier(sessions, repository, tg))
    assert outcome.status == "success"
    assert sorted(c for c, _ in tg.sent) == ["111", "222"]
    assert "01.07.2026" in tg.sent[0][1] and "02.07.2026" in tg.sent[0][1]
    assert await deliveries(sessions) == [("111", "sent", 1, None), ("222", "sent", 1, None)]


async def test_same_run_is_never_sent_twice(repository, sessions, engine, two_recipients):
    tg = FakeTelegram()
    notifier = make_notifier(sessions, repository, tg)
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), repository, sessions, engine, notifier)
    await notifier.notify_run(outcome.run_id, outcome.changed_days)  # повторна обробка того самого запуску
    assert len(tg.sent) == 2


async def test_one_recipient_failure_does_not_stop_others(repository, sessions, engine, two_recipients):
    tg = FakeTelegram(fail={"111": 403})
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), repository, sessions, engine, make_notifier(sessions, repository, tg))
    assert outcome.status == "success"
    [(c1, s1, a1, e1), (c2, s2, _, _)] = await deliveries(sessions)
    assert (c1, s1) == ("111", "failed") and "blocked by the user" in e1
    assert a1 == 1  # 403 не повторюється: у журналі фактичні спроби, а не максимум
    assert (c2, s2) == ("222", "sent")


async def test_5xx_is_recorded_as_one_failed_attempt(repository, sessions, engine, two_recipients):
    tg = FakeTelegram(fail={"111": 502})
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), repository, sessions, engine, make_notifier(sessions, repository, tg))
    assert outcome.status == "success"
    [(c1, s1, a1, e1), (c2, s2, a2, _)] = await deliveries(sessions)
    assert (c1, s1, a1) == ("111", "failed", 1) and "HTTP 502" in e1
    assert (c2, s2, a2) == ("222", "sent", 1)


async def test_recalculated_day_is_marked(repository, sessions, engine, two_recipients):
    await collect(FakeDamSource({Q3: q3_file(2)}), repository, sessions, engine, None)
    tg = FakeTelegram()
    edited = q3_file(3, changed={date(2026, 7, 2): "555.55"})
    await collect(FakeDamSource({Q3: edited}), repository, sessions, engine, make_notifier(sessions, repository, tg))
    text = tg.sent[0][1]
    assert "02.07.2026 (перераховано)" in text
    assert "03.07.2026\n" in text and "03.07.2026 (перераховано)" not in text


@pytest.mark.parametrize("kind", ["no_changes", "no_data", "error"])
async def test_non_success_sends_nothing(kind, repository, sessions, engine, two_recipients):
    tg = FakeTelegram()
    notifier = make_notifier(sessions, repository, tg)
    if kind == "no_changes":
        await collect(FakeDamSource({Q3: q3_file(2)}), repository, sessions, engine, None)
        source = FakeDamSource({Q3: q3_file(2)})
    elif kind == "no_data":
        source = FakeDamSource()
    else:
        source = DownSource()
    outcome = await collect(source, repository, sessions, engine, notifier)
    assert outcome.status == kind
    assert tg.sent == []


async def test_skipped_locked_sends_nothing(repository, sessions, engine, two_recipients, held_lock):
    tg = FakeTelegram()
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), repository, sessions, engine, make_notifier(sessions, repository, tg))
    assert outcome.status == "skipped_locked" and tg.sent == []


async def test_notifier_exception_does_not_change_run_status(repository, sessions, engine, two_recipients):
    class Broken(Notifier):
        async def _notify(self, *a):
            raise RuntimeError("зламано")
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), repository, sessions, engine,
                            Broken(sessions, repository, TelegramClient(TOKEN)))
    assert outcome.status == "success"
    assert (await RunLog(sessions).get(outcome.run_id)).status == "success"


async def test_without_token_notifications_are_off(repository, sessions, engine, two_recipients, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    calls = []
    monkeypatch.setattr(httpx.AsyncClient, "post", lambda *a, **k: calls.append(a))
    notifier = notifier_from_env(sessions, repository)
    assert notifier.client is None
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), repository, sessions, engine, notifier)
    assert outcome.status == "success" and calls == [] and await deliveries(sessions) == []


async def test_backfill_never_notifies(repository, engine, sessions, two_recipients, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    calls = []
    monkeypatch.setattr(httpx.AsyncClient, "post", lambda *a, **k: calls.append(a))
    code = await run_locked_backfill(engine, FakeDamSource({Q3: q3_file(2)}), repository, [Q3], delay=0, out=io.StringIO())
    assert code == 0 and calls == []


def test_app_and_cli_wire_the_notifier_backfill_does_not():
    import inspect
    from app import backfill
    from app.api import app as api_app
    from app.collection import collect as collect_mod
    assert "notifier=dam_notifier" in inspect.getsource(api_app)
    assert "notifier=notifier_from_env" in inspect.getsource(collect_mod)
    assert "notif" not in inspect.getsource(backfill)


# Глобальний вимикач

async def test_switched_off_sends_nothing_and_records_no_deliveries(repository, sessions, engine, two_recipients):
    from app.settings import NotificationSettingsStore
    await NotificationSettingsStore(sessions).set_enabled(False)
    tg = FakeTelegram()
    outcome = await collect(FakeDamSource({Q3: q3_file(2)}), repository, sessions, engine, make_notifier(sessions, repository, tg))
    assert outcome.status == "success"
    assert tg.sent == [] and await deliveries(sessions) == []


async def test_reenabling_does_not_resend_missed_runs(repository, sessions, engine, two_recipients):
    from app.settings import NotificationSettingsStore
    switch = NotificationSettingsStore(sessions)
    tg = FakeTelegram()
    notifier = make_notifier(sessions, repository, tg)
    await switch.set_enabled(False)
    missed = await collect(FakeDamSource({Q3: q3_file(2)}), repository, sessions, engine, notifier)
    await switch.set_enabled(True)
    await notifier.notify_run(missed.run_id, [])  # нічого не змінилось — дорозсилання немає
    assert tg.sent == [] and await deliveries(sessions) == []
    later = await collect(FakeDamSource({Q3: q3_file(3)}), repository, sessions, engine, notifier)
    assert later.status == "success"
    assert sorted(c for c, _ in tg.sent) == ["111", "222"]
