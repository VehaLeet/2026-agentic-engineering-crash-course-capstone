"""Кандидати в отримувачі з оновлень бота (getUpdates): хто писав боту або додав його в чат."""

from dataclasses import dataclass
from datetime import datetime, timezone

# Оновлення, що несуть чат. Решту типів відкидаємо: allowed_updates свідомо не звужуємо (див. TelegramClient).
_CHAT_UPDATES = ("message", "edited_message", "channel_post", "edited_channel_post", "my_chat_member")
_GONE = ("left", "kicked")  # бота видалили з групи/каналу або людина його заблокувала


@dataclass(frozen=True, slots=True)
class Candidate:
    chat_id: str
    type: str
    title: str
    username: str | None
    last_seen_at: datetime


def _title(chat: dict) -> str:
    if chat.get("title"):
        return chat["title"]
    return " ".join(p for p in (chat.get("first_name"), chat.get("last_name")) if p)


def candidates_from_updates(updates: list[dict]) -> list[Candidate]:
    """Один запис на чат з його останнім станом; найновіші першими."""
    latest: dict[int, Candidate | None] = {}
    for update in sorted(updates, key=lambda u: u.get("update_id", 0)):
        kind = next((k for k in _CHAT_UPDATES if k in update), None)
        if kind is None:
            continue
        body = update[kind]
        chat = body.get("chat") or {}
        if "id" not in chat:
            continue
        if kind == "my_chat_member" and (body.get("new_chat_member") or {}).get("status") in _GONE:
            latest[chat["id"]] = None
            continue
        latest[chat["id"]] = Candidate(
            chat_id=str(chat["id"]), type=chat.get("type", ""), title=_title(chat),
            username=chat.get("username"),
            last_seen_at=datetime.fromtimestamp(body.get("edit_date") or body.get("date", 0), timezone.utc),
        )
    return sorted((c for c in latest.values() if c is not None), key=lambda c: c.last_seen_at, reverse=True)
