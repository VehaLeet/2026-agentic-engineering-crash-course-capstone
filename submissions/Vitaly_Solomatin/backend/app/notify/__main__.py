"""CLI сповіщень: `uv run python -m app.notify recipients add|list|remove <chat_id>` і `... test`."""

import argparse
import asyncio
import sys

from app.notify.message import TEST_TEXT
from app.notify.notifier import telegram_from_env
from app.notify.recipients import InvalidChatId, RecipientRepository
from app.notify.telegram import TelegramClient, TelegramError



async def main(argv: list[str] | None = None, client: TelegramClient | None = None, sessions=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.notify", description="Сповіщення Telegram")
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("recipients", help="керування отримувачами")
    rec_sub = rec.add_subparsers(dest="action", required=True)
    rec_sub.add_parser("list")
    for action in ("add", "remove"):
        rec_sub.add_parser(action).add_argument("chat_id")
    sub.add_parser("test", help="надіслати тестове повідомлення всім увімкненим отримувачам")
    args = parser.parse_args(argv)

    engine = None
    if sessions is None:
        from app.storage.database import make_engine, make_session_factory
        engine = make_engine()
        sessions = make_session_factory(engine)
    try:
        repo = RecipientRepository(sessions)
        if args.command == "recipients":
            return await _recipients(repo, args)
        return await _test(repo, client or telegram_from_env())
    finally:
        if engine is not None:
            await engine.dispose()


async def _recipients(repo: RecipientRepository, args) -> int:
    if args.action == "list":
        rows = await repo.all()
        if not rows:
            print("отримувачів немає")
        for r in rows:
            print(f"{r.chat_id}\t{'увімкнено' if r.enabled else 'вимкнено'}")
        return 0
    if args.action == "add":
        try:
            added = await repo.add(args.chat_id)
        except InvalidChatId as e:
            print(f"помилка: {e}", file=sys.stderr)
            return 2
        print(f"{args.chat_id}: {'додано' if added else 'вже є'}")
        return 0
    removed = await repo.remove(args.chat_id)
    print(f"{args.chat_id}: {'видалено' if removed else 'не знайдено'}")
    return 0 if removed else 1


async def _test(repo: RecipientRepository, client: TelegramClient | None) -> int:
    if client is None:
        print("TELEGRAM_BOT_TOKEN не задано", file=sys.stderr)
        return 2
    chat_ids = await repo.enabled()
    if not chat_ids:
        print("немає увімкнених отримувачів: додайте `recipients add <chat_id>`", file=sys.stderr)
        return 1
    failed = 0
    for chat_id in chat_ids:
        try:
            await client.send(chat_id, TEST_TEXT)
            print(f"{chat_id}\tOK")
        except TelegramError as e:  # текст уже без токена
            failed += 1
            print(f"{chat_id}\tПОМИЛКА: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
