from datetime import datetime, timezone

from app.notify.candidates import candidates_from_updates

T0 = 1_790_000_000  # unix-час, довільна точка

OLENA = {"id": 987654321, "type": "private", "first_name": "Олена", "username": "olena"}
IVAN = {"id": 111, "type": "private", "first_name": "Іван", "last_name": "Петренко"}
CHANNEL = {"id": -1001234567890, "type": "channel", "title": "Ціни РДН", "username": "oree_dam"}
GROUP = {"id": -555, "type": "group", "title": "Команда"}


def message(uid, chat, t, text="/start"):
    return {"update_id": uid, "message": {"message_id": uid, "chat": chat, "date": t, "text": text}}


def member(uid, chat, t, status):
    return {"update_id": uid, "my_chat_member": {"chat": chat, "date": t, "new_chat_member": {"status": status}}}


def utc(t):
    return datetime.fromtimestamp(t, timezone.utc)


def test_private_start():
    [c] = candidates_from_updates([message(1, OLENA, T0)])
    assert (c.chat_id, c.type, c.title, c.username, c.last_seen_at) == ("987654321", "private", "Олена", "olena", utc(T0))


def test_full_name_without_username():
    [c] = candidates_from_updates([message(1, IVAN, T0)])
    assert (c.title, c.username) == ("Іван Петренко", None)


def test_channel_via_membership_and_post():
    updates = [member(1, CHANNEL, T0, "administrator"),
               {"update_id": 2, "channel_post": {"chat": CHANNEL, "date": T0 + 5, "text": "x"}}]
    [c] = candidates_from_updates(updates)
    assert (c.chat_id, c.type, c.title, c.last_seen_at) == ("-1001234567890", "channel", "Ціни РДН", utc(T0 + 5))


def test_one_entry_per_chat_with_latest_time():
    [c] = candidates_from_updates([message(1, OLENA, T0), message(2, OLENA, T0 + 60), message(3, OLENA, T0 + 120)])
    assert c.last_seen_at == utc(T0 + 120)


def test_removed_or_blocked_chats_are_excluded():
    updates = [member(1, GROUP, T0, "member"), member(2, GROUP, T0 + 1, "left"),
               message(3, OLENA, T0 + 2), member(4, OLENA, T0 + 3, "kicked")]
    assert candidates_from_updates(updates) == []


def test_re_added_group_is_present():
    updates = [member(1, GROUP, T0, "member"), member(2, GROUP, T0 + 1, "kicked"), member(3, GROUP, T0 + 2, "member")]
    [c] = candidates_from_updates(updates)
    assert c.chat_id == "-555"


def test_noise_ignored_and_order_newest_first():
    updates = [message(2, IVAN, T0 + 10), {"update_id": 3, "callback_query": {"id": "x"}},
               {"update_id": 4, "message": {"date": T0}}, message(1, OLENA, T0)]
    assert [c.chat_id for c in candidates_from_updates(updates)] == ["111", "987654321"]


def test_empty():
    assert candidates_from_updates([]) == []
