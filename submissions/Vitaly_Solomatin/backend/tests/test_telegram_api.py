import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import func, select

from app.api.app import create_app
from app.collection.runs import RunLog
from app.notify.message import TEST_TEXT
from app.notify.recipients import RecipientRepository
from app.notify.telegram import TelegramClient
from app.storage.models import NotificationDelivery
from tests.fakes import FakeDamSource
from tests.test_candidates import CHANNEL, OLENA, T0, member, message
from tests.test_notifier import TOKEN, no_sleep
from tests.test_notify_cli import run as run_cli


class FakeBotApi:
    """Підставний Bot API: getUpdates віддає задані оновлення, sendMessage записує або відмовляє."""

    def __init__(self, updates=None, fail=None, updates_status=200):
        self.updates = updates or []
        self.fail = fail or {}
        self.updates_status = updates_status
        self.calls: list[str] = []
        self.sent: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        self.calls.append(method)
        body = json.loads(request.content)
        if method == "getUpdates":
            if self.updates_status != 200:
                return httpx.Response(self.updates_status, json={
                    "ok": False, "description": "Conflict: can't use getUpdates method while webhook is active"})
            return httpx.Response(200, json={"ok": True, "result": self.updates})
        code = self.fail.get(body["chat_id"])
        if code:
            return httpx.Response(code, json={"ok": False, "description": "Forbidden: bot can't initiate conversation with a user"})
        self.sent.append((body["chat_id"], body["text"]))
        return httpx.Response(200, json={"ok": True, "result": {}})


def bot_client(api) -> TelegramClient:
    return TelegramClient(TOKEN, transport=httpx.MockTransport(api), sleep=no_sleep)


@asynccontextmanager
async def settings_app(engine, telegram):
    app = create_app(engine=engine, source=FakeDamSource(), scheduler=False, telegram=telegram)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def deliveries(sessions) -> int:
    async with sessions() as s:
        return (await s.execute(select(func.count()).select_from(NotificationDelivery))).scalar_one()


# 1. Вимикач

async def test_notifications_default_and_no_token_leak(engine):
    async with settings_app(engine, bot_client(FakeBotApi())) as client:
        r = await client.get("/settings/notifications")
    assert r.status_code == 200 and r.json() == {"enabled": True, "token_configured": True}
    assert TOKEN not in r.text and "SECRET" not in r.text


async def test_notifications_without_token(engine):
    async with settings_app(engine, None) as client:
        assert (await client.get("/settings/notifications")).json()["token_configured"] is False


async def test_notifications_switch_survives_restart(engine):
    async with settings_app(engine, None) as client:
        r = await client.put("/settings/notifications", json={"enabled": False})
        assert r.status_code == 200 and r.json()["enabled"] is False
    async with settings_app(engine, None) as client:
        assert (await client.get("/settings/notifications")).json()["enabled"] is False


@pytest.mark.parametrize("body", [{"enabled": "false"}, {}])
async def test_notifications_invalid_body(engine, body):
    async with settings_app(engine, None) as client:
        assert (await client.put("/settings/notifications", json=body)).status_code == 422
        assert (await client.get("/settings/notifications")).json()["enabled"] is True


# 2. Перелік і додавання

async def test_list_in_insertion_order_and_empty(engine, sessions):
    async with settings_app(engine, None) as client:
        assert (await client.get("/settings/telegram/recipients")).json() == []
        await client.post("/settings/telegram/recipients", json={"chat_id": "123456789"})
        await client.post("/settings/telegram/recipients", json={"chat_id": "-1001234567890"})
        await client.patch("/settings/telegram/recipients/-1001234567890", json={"enabled": False})
        r = await client.get("/settings/telegram/recipients")
    assert r.json() == [{"chat_id": "123456789", "enabled": True}, {"chat_id": "-1001234567890", "enabled": False}]


async def test_add_new_and_existing_disabled(engine, sessions):
    async with settings_app(engine, None) as client:
        r = await client.post("/settings/telegram/recipients", json={"chat_id": "123456789"})
        assert r.status_code == 201 and r.json() == {"chat_id": "123456789", "enabled": True}
        await client.patch("/settings/telegram/recipients/123456789", json={"enabled": False})
        r = await client.post("/settings/telegram/recipients", json={"chat_id": "123456789"})
        assert r.status_code == 200 and r.json() == {"chat_id": "123456789", "enabled": False}
    assert len(await RecipientRepository(sessions).all()) == 1


@pytest.mark.parametrize("body", [{"chat_id": "hello world"}, {}])
async def test_add_invalid(engine, sessions, body):
    async with settings_app(engine, None) as client:
        r = await client.post("/settings/telegram/recipients", json=body)
    assert r.status_code == 422
    if body:
        assert "@channel" in r.text
    assert await RecipientRepository(sessions).all() == []


async def test_added_via_api_visible_in_cli(engine, sessions, capsys):
    async with settings_app(engine, None) as client:
        await client.post("/settings/telegram/recipients", json={"chat_id": "123456789"})
    code, out = await run_cli(capsys, sessions, "recipients", "list")
    assert "123456789" in out


# 3. Зміна і видалення

async def test_patch_disable_channel_and_unknown(engine, sessions):
    async with settings_app(engine, None) as client:
        await client.post("/settings/telegram/recipients", json={"chat_id": "@oree_dam"})
        r = await client.patch("/settings/telegram/recipients/@oree_dam", json={"enabled": False})
        assert r.status_code == 200 and r.json() == {"chat_id": "@oree_dam", "enabled": False}
        assert (await client.patch("/settings/telegram/recipients/555", json={"enabled": True})).status_code == 404


async def test_patch_non_bool_keeps_state(engine, sessions):
    async with settings_app(engine, None) as client:
        await client.post("/settings/telegram/recipients", json={"chat_id": "123456789"})
        r = await client.patch("/settings/telegram/recipients/123456789", json={"enabled": "no"})
        assert r.status_code == 422
    assert (await RecipientRepository(sessions).get("123456789")).enabled is True


async def test_delete_keeps_delivery_history(engine, sessions):
    await RecipientRepository(sessions).add("123456789")
    run_id = await RunLog(sessions).start("manual")
    async with sessions() as s, s.begin():
        s.add(NotificationDelivery(run_id=run_id, chat_id="123456789", status="sent",
                                   created_at=datetime.now(timezone.utc)))
    async with settings_app(engine, None) as client:
        assert (await client.delete("/settings/telegram/recipients/123456789")).status_code == 204
        assert (await client.get("/settings/telegram/recipients")).json() == []
        assert (await client.delete("/settings/telegram/recipients/555")).status_code == 404
    assert await deliveries(sessions) == 1


# 4. Тестове повідомлення

async def test_test_message_ok(engine, sessions):
    api = FakeBotApi()
    await RecipientRepository(sessions).add("123456789")
    async with settings_app(engine, bot_client(api)) as client:
        r = await client.post("/settings/telegram/recipients/123456789/test")
    assert r.status_code == 200 and r.json() == {"ok": True, "error": None}
    assert api.sent == [("123456789", TEST_TEXT)]
    assert await deliveries(sessions) == 0


async def test_test_message_forbidden(engine, sessions):
    await RecipientRepository(sessions).add("123456789")
    async with settings_app(engine, bot_client(FakeBotApi(fail={"123456789": 403}))) as client:
        body = (await client.post("/settings/telegram/recipients/123456789/test")).json()
    assert body["ok"] is False and "can't initiate conversation" in body["error"]
    assert TOKEN not in body["error"]


async def test_test_message_ignores_recipient_and_global_switches(engine, sessions):
    api = FakeBotApi()
    repo = RecipientRepository(sessions)
    await repo.add("123456789")
    await repo.set_enabled("123456789", False)
    async with settings_app(engine, bot_client(api)) as client:
        await client.put("/settings/notifications", json={"enabled": False})
        assert (await client.post("/settings/telegram/recipients/123456789/test")).json()["ok"] is True
    assert len(api.sent) == 1


async def test_test_message_unknown_and_no_token(engine, sessions):
    api = FakeBotApi()
    async with settings_app(engine, bot_client(api)) as client:
        assert (await client.post("/settings/telegram/recipients/555/test")).status_code == 404
    assert api.calls == []
    await RecipientRepository(sessions).add("123456789")
    async with settings_app(engine, None) as client:
        r = await client.post("/settings/telegram/recipients/123456789/test")
    assert r.status_code == 409 and "TELEGRAM_BOT_TOKEN" in r.text


# 5. Кандидати

async def test_candidates_with_added_flags(engine, sessions):
    other = {"id": 42, "type": "private", "first_name": "Інша"}
    api = FakeBotApi(updates=[message(1, OLENA, T0), member(2, CHANNEL, T0 + 5, "administrator"),
                              message(3, other, T0 + 10)])
    repo = RecipientRepository(sessions)
    await repo.add("987654321")
    await repo.add("@oree_dam")
    async with settings_app(engine, bot_client(api)) as client:
        first = (await client.get("/settings/telegram/candidates")).json()
        second = (await client.get("/settings/telegram/candidates")).json()
    assert first == second
    assert [(c["chat_id"], c["added"]) for c in first] == [("42", False), ("-1001234567890", True), ("987654321", True)]
    olena = first[-1]
    assert (olena["type"], olena["title"], olena["username"]) == ("private", "Олена", "olena")
    assert datetime.fromisoformat(olena["last_seen_at"]) == datetime.fromtimestamp(T0, timezone.utc)
    assert "sendMessage" not in api.calls


async def test_candidates_no_token(engine):
    async with settings_app(engine, None) as client:
        r = await client.get("/settings/telegram/candidates")
    assert r.status_code == 409 and "TELEGRAM_BOT_TOKEN" in r.text


async def test_candidates_webhook_conflict(engine):
    async with settings_app(engine, bot_client(FakeBotApi(updates_status=409))) as client:
        r = await client.get("/settings/telegram/candidates")
    assert r.status_code == 502 and "webhook is active" in r.text and TOKEN not in r.text


async def test_candidates_network_failure(engine):
    def down(request):
        raise httpx.ConnectError(f"cannot connect to {request.url}")

    async with settings_app(engine, bot_client(down)) as client:
        r = await client.get("/settings/telegram/candidates")
    assert r.status_code == 502 and TOKEN not in r.text and "SECRET" not in r.text
