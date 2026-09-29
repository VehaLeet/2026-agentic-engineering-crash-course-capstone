## Context

- `TelegramClient` (`app/notify/telegram.py`) уміє лише `sendMessage`: таймаут, до 3 спроб на
  мережу, 5xx і 429 з `retry_after`, без повторів на 400/403, токен вирізається з текстів помилок.
- `RecipientRepository` має `all`, `enabled`, `add` (з `validate_chat_id`) і `remove`. Змінити
  ознаку `enabled` зараз не можна ніяк, хоча колонка є.
- `Notifier._notify` виходить одразу, коли клієнта немає (токен не задано). Глобального вимикача
  немає.
- `create_app` будує `Notifier` через `notifier_from_env`, тож Telegram-клієнт живе всередині
  нотифікатора і тестам недоступний окремо.
- Зріз 8 створив однорядкову `app_settings` і `ScheduleSettingsStore` з самолікуванням рядка.

## Goals / Non-Goals

**Goals:**
- Один Telegram-клієнт у процесі API: ним користуються і розсилка, і нові маршрути.
- Розбір оновлень Telegram — чиста функція, яку тестують на JSON без мережі.
- Жодних нових залежностей і жодного фонового опитування Telegram.

**Non-Goals:**
- Кешування кандидатів чи відповіді `getUpdates` між запитами.
- Уніфікація всіх налаштувань в одному ендпойнті: розклад, сповіщення й отримувачі — окремі ресурси.

## Decisions

### 1. Один приватний `_call` у `TelegramClient`

`send` переписується на спільний `_call(method, body) -> dict`, який містить уже наявну логіку
спроб і повертає `result` із відповіді. Поруч з'являється:

```
async def get_updates(self) -> list[dict]:
    return await self._call("getUpdates", {"timeout": 0, "limit": 100})
```

`timeout: 0` — коротке опитування: запит повертається одразу, HTTP-запит до API не висить.
Відповідь 409 (активний webhook) не входить у список повторюваних кодів і стає `TelegramError`
з описом від Telegram. Поведінка `send` не змінюється, і наявні тести `send` це підтверджують.

*Альтернатива:* окремий метод із власним циклом повторів. Відкинуто, бо це дублювання логіки, що
вже покрита тестами.

### 2. Без `offset` і без `allowed_updates`

- **`offset` не передаємо.** Виклик із `offset` підтверджує оновлення, і Telegram їх видаляє.
  Без нього оновлення лежать до 24 годин, і повторний запит бачить ті самі чати: так і вимагає
  специфікація. Ціна рішення: якщо непідтверджених оновлень понад 100, видно лише 100
  найстаріших. Для внутрішнього бота на 1–5 людей це не проблема (див. Risks).
- **`allowed_updates` не передаємо.** Цей параметр Telegram *запам'ятовує* для бота, тож
  запит на читання мовчки змінив би налаштування бота. Типовий набір уже містить `message`,
  `edited_message`, `channel_post`, `edited_channel_post` і `my_chat_member`, а решту типів ми
  відкидаємо локально.

### 3. Розбір кандидатів: `app/notify/candidates.py`

```
@dataclass(frozen=True)
class Candidate:
    chat_id: str; type: str; title: str; username: str | None; last_seen_at: datetime

def candidates_from_updates(updates: list[dict]) -> list[Candidate]
```

- Оновлення проходять за зростанням `update_id`. Для кожного чату лишається останній стан.
- Джерело чату: `message`, `edited_message`, `channel_post`, `edited_channel_post` (поле
  `chat`) і `my_chat_member` (поле `chat`, плюс `new_chat_member.status`).
- Якщо останнє оновлення чату — `my_chat_member` зі статусом `left` або `kicked`, чат
  прибирається. У приватному чаті `kicked` означає, що людина заблокувала бота.
- `title`: `chat.title` для груп і каналів, інакше `first_name` і `last_name` через пробіл.
  `last_seen_at`: поле `date` оновлення (unix-час), переведене в UTC.
- Сортування за `last_seen_at` від найновішого. Невідомі типи оновлень і оновлення без чату
  ігноруються.

Позначка `added` рахується в маршруті, а не в розборі: `str(chat.id)` є в переліку отримувачів,
або для каналу з username у переліку є `@username`.

### 4. Вимикач сповіщень у `app_settings`

Міграція `0005_notifications_enabled`:

```
ALTER TABLE app_settings ADD COLUMN notifications_enabled BOOLEAN NOT NULL DEFAULT true
```

У `app/settings.py` з'являється `NotificationSettingsStore` з методами `enabled()` і
`set_enabled(value)`. Він так само самолікує рядок через `INSERT ... ON CONFLICT DO NOTHING`.
`Notifier` створює його зі своїх `sessions` і перевіряє вимикач у `_notify` після перевірки
клієнта, **до** будь-якого `_claim`: доставки не створюються зовсім, як і вимагає специфікація.
Вимикач читається на кожен запуск, тож кешу, який треба скидати після `PUT`, немає.

Тестове повідомлення (API і CLI `test`) вимикач не перевіряє: це ручна діагностика, а не
сповіщення.

### 5. Telegram-клієнт у `create_app`

```
create_app(..., telegram: TelegramClient | None | Unset = UNSET)
```

`UNSET` означає «з env» (`telegram_from_env()`), а `None` — явно без токена. У `lifespan` клієнт
кладеться в `app.state.telegram`, і з нього ж будується нотифікатор:
`notifier or Notifier(sessions, repository, client)`, з тим самим попередженням у лог, коли токена
немає. `notifier_from_env` лишається для CLI збору. `token_configured` — це
`app.state.telegram is not None`.

### 6. Маршрути: окремий `APIRouter`

`app/api/telegram_routes.py` з `router = APIRouter()`, підключеним у `create_app`. `app.py` уже
близько 200 рядків, і налаштування Telegram — окрема тема.

```
GET    /settings/notifications                      200 {"enabled": bool, "token_configured": bool}
PUT    /settings/notifications   {"enabled": StrictBool}         200 | 422

GET    /settings/telegram/recipients                200 [{"chat_id": str, "enabled": bool}]
POST   /settings/telegram/recipients {"chat_id": StrictStr}      201 new | 200 existing | 422
PATCH  /settings/telegram/recipients/{chat_id} {"enabled": StrictBool}  200 | 404 | 422
DELETE /settings/telegram/recipients/{chat_id}      204 | 404
POST   /settings/telegram/recipients/{chat_id}/test 200 {"ok": true} | {"ok": false, "error": str}
                                                    404 unknown | 409 no token
GET    /settings/telegram/candidates                200 [{"chat_id", "type", "title", "username",
                                                          "last_seen_at", "added"}]
                                                    409 no token | 502 Telegram error
```

- `InvalidChatId` з `validate_chat_id` перетворюється на 422 з тим самим текстом, що в CLI.
- Порядок перевірок у `/test`: спершу отримувач (404), потім токен (409). Так невідомий
  отримувач ніколи не звертається до Telegram.
- Відмова Telegram у `/test` — це 200 з `ok: false`: сама перевірка виконалась, її результат і є
  відповіддю. 502 лишається для кандидатів, де без відповіді Telegram повернути нічого.
- Текст тестового повідомлення: наявна константа `TEST_TEXT` переїжджає з
  `app/notify/__main__.py` у `app/notify/message.py`, щоб CLI і API слали однакове.

### 7. Нові методи `RecipientRepository`

`get(chat_id) -> Recipient | None` і `set_enabled(chat_id, enabled) -> Recipient | None`
(`UPDATE ... RETURNING`). `POST` викликає `add`, а потім `get`: `add` повертає `True` → 201,
`False` → 200 з поточним станом.

## Risks / Trade-offs

- [Понад 100 непідтверджених оновлень — нові чати не видно] → ризик низький для 1–5 людей;
  оновлення зникають за 24 години. Якщо стане проблемою, наступний крок — підтверджувати
  `offset` і зберігати кандидатів у БД.
- [Кандидати живуть лише 24 години] → людині, яка писала боту давно, достатньо написати ще раз;
  UI 11b покаже підказку.
- [`/test` може тривати до ~35 с при недоступному Telegram: 3 спроби по 10 с плюс паузи] →
  прийнятно для кнопки діагностики; UI 11b має показувати очікування.
- [Хтось налаштує webhook для цього бота деінде → кандидати дають 502] → текст Telegram про
  webhook повертається як є, і його зрозуміло без документації.
- [Канал доданий як `@name`, а кандидат має числовий id] → `added` звіряє і `@username`;
  приватний канал без username збігатиметься лише за id.
- [Імена людей у відповіді кандидатів] → API слухає лише localhost, як і решта даних сервісу.

## Migration Plan

1. `alembic upgrade head` додає `notifications_enabled = true` до наявного рядка. Поведінка до
   першого `PUT` та сама, що зараз. Відкат: `alembic downgrade 0004_app_settings`.
2. Нових env-змінних немає. Без `TELEGRAM_BOT_TOKEN` API отримувачів працює, а кандидати й
   тести відповідають 409.
