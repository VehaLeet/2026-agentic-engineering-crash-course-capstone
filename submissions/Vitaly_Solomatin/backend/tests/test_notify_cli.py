import httpx
import pytest

from app.notify import __main__ as cli
from app.notify.telegram import TelegramClient
from tests.test_notifier import TOKEN, FakeTelegram, no_sleep


async def run(capsys, sessions, *argv, client=None):
    code = await cli.main(list(argv), client=client, sessions=sessions)
    out = capsys.readouterr()
    return code, out.out + out.err


async def test_recipients_add_list_remove(sessions, capsys):
    assert (await run(capsys, sessions, "recipients", "add", "123456789"))[0] == 0
    code, out = await run(capsys, sessions, "recipients", "add", "123456789")
    assert code == 0 and "вже є" in out
    code, out = await run(capsys, sessions, "recipients", "list")
    assert "123456789\tувімкнено" in out
    assert (await run(capsys, sessions, "recipients", "remove", "123456789"))[0] == 0
    code, out = await run(capsys, sessions, "recipients", "list")
    assert "отримувачів немає" in out


async def test_invalid_chat_id_is_rejected(sessions, capsys):
    code, out = await run(capsys, sessions, "recipients", "add", "hello")
    assert code == 2 and "некоректний chat_id" in out


async def test_test_command_reports_each_and_fails_on_one_error(sessions, capsys):
    await run(capsys, sessions, "recipients", "add", "111")
    await run(capsys, sessions, "recipients", "add", "222")
    tg = FakeTelegram(fail={"222": 400})
    client = TelegramClient(TOKEN, transport=httpx.MockTransport(tg), sleep=no_sleep)
    code, out = await run(capsys, sessions, "test", client=client)
    assert code == 1
    assert "111\tOK" in out and "222\tПОМИЛКА" in out
    assert TOKEN not in out


async def test_test_command_without_token(sessions, capsys, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    code, out = await run(capsys, sessions, "test")
    assert code == 2 and "TELEGRAM_BOT_TOKEN не задано" in out
