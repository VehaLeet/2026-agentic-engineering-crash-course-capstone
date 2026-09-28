## Context

Мотивація і межі — у `proposal.md`, вимоги — у `specs/telegram-notify/spec.md`.

Що вже є:

- `collect_once` (`app/collection/collect.py`): бере блокування, отримує `result.day_hashes`,
  читає збережені хеші `stored = get_day_hashes(...)`, рахує `changed`, зберігає, робить
  `runs.finish(run_id, "success", changed)` і повертає `CollectOutcome`. Сповіщення має
  спрацювати саме тут, після фіксації `success`.
- `DamRepository.get_daily(from, to)` повертає `DailyPrices`: `price_min`, `price_max`,
  `price_weighted` (зважена за обсягом продажу, для 26.09.2026 = 6560.60, як у ОРЕЕ).
- Бекфіл (`app/backfill.py`) пише через `save_quarter` і `collect_once` не викликає.
- Міграції `0001`, `0002`. Тести на Postgres через testcontainers; HTTP підміняється
  `httpx.MockTransport`, як у тестах `dam-source`.
- `TELEGRAM_BOT_TOKEN` згадано в брифі як секрет, але в коді його ще немає.

## Goals / Non-Goals

**Goals:**

- Не більше одного повідомлення на запуск для одного отримувача, гарантоване схемою, а не
  дисципліною коду.
- Збій Telegram не впливає ні на збір, ні на інших отримувачів.
- Токен ніде не видно.
- Усе тестується без мережі.

**Non-Goals:**

- Автоматичне дорозсилання `pending` після загибелі процесу: MVP лишає їх видимими.
- Черги повідомлень і воркери.

## Decisions

### Де викликається сповіщення

```
collect_once
  ... save_collected(...)                        # дані зафіксовано
  runs.finish(run_id, "success", changed)        # запуск зафіксовано
  await notifier.notify_run(run_id, changed, recalculated)   # <- нове
  return CollectOutcome(...)
```

`recalculated = [d for d in changed if d in stored]`. Доба, яка вже мала хеш до збереження і
змінилась, вважається перерахованою. Додатковий запит не потрібен, бо `stored` уже прочитано для
діфу.

Сповіщення викликається **після** `runs.finish`, поза `try` збору. Будь-який виняток нотифікатора
перехоплюється й логується всередині `notify_run`, тож статус запуску від доставки не залежить.
Нотифікатор викликається всередині `dam_writer_lock`. Коли ОРЕЕ публікує дані, це подовжує
блокування на кілька секунд, але не дає наступному запуску почати надсилати про ту саму зміну,
поки не закінчилась перша розсилка.

`collect_once` отримує необов'язковий параметр `notifier`. Без нього, наприклад у наявних
тестах, поведінка не змінюється. Застосунок (HTTP) і CLI `collect` передають справжній
нотифікатор. Бекфіл його не отримує, тож не сповіщає за побудовою.

### Схема

```
telegram_recipients
  id          BIGINT IDENTITY PK
  chat_id     TEXT NOT NULL UNIQUE      -- ціле (зокрема від'ємне) або @channel
  enabled     BOOLEAN NOT NULL DEFAULT true
  created_at  TIMESTAMPTZ NOT NULL

notification_deliveries
  id            BIGINT IDENTITY PK
  run_id        BIGINT NOT NULL REFERENCES collection_runs(id)
  chat_id       TEXT NOT NULL             -- копія, щоб видалення отримувача не губило історію
  status        TEXT NOT NULL CHECK (status IN ('pending','sent','failed'))
  attempts      SMALLINT NOT NULL DEFAULT 0
  error_message TEXT
  created_at    TIMESTAMPTZ NOT NULL
  finished_at   TIMESTAMPTZ
  UNIQUE (run_id, chat_id)                -- гарантія «не більше одного»
```

`chat_id` у доставці зберігається текстом, без зовнішнього ключа на отримувача. Отримувача можна
видалити, а історія доставок має лишитися.

### «Не більше одного» — через `INSERT ... ON CONFLICT DO NOTHING`

```
для кожного ввімкненого отримувача:
  INSERT delivery(run_id, chat_id, 'pending') ON CONFLICT DO NOTHING RETURNING id
  нічого не вставлено  -> доставка вже є: пропустити (ніколи не надсилати вдруге)
  вставлено            -> send() -> UPDATE status sent|failed, attempts, error, finished_at
```

Запис створюється **до** відправки. Якщо процес загине між записом і відправкою, лишиться
`pending`, і повідомлення не надійде. Це свідомий вибір «не більше одного разу»: дубль у
Telegram гірший за пропуск, бо пропуск видно в журналі, а дубль уже не відкликати. Автоматичне
дорозсилання `pending` — поза MVP.

### Клієнт Bot API

```
POST https://api.telegram.org/bot<TOKEN>/sendMessage
     {"chat_id": ..., "text": ..., "disable_web_page_preview": true}
```

- Таймаут 10 с, до 3 спроб.
- Повтор на мережеву помилку, 5xx і 429. На 429 чекаємо `parameters.retry_after` з тіла
  відповіді; якщо його немає, експоненційна пауза 1 с, 2 с.
- 400 і 403 без повтору: у тексті помилки описання з тіла Telegram (`description`).
- `sleep` передається параметром, тести не чекають реально.
- Текст без `parse_mode`: звичайний текст не ламається на спецсимволах у даних.

**Захист токена.** URL містить токен, а `httpx` вставляє URL у повідомлення винятків. Будь-який
текст помилки проходить через `redact(text)`, який замінює токен на `***`. Тести стверджують,
що токен не з'являється ні в журналі доставок, ні в журналі запусків, ні у виводі CLI.

### Повідомлення

```
РДН: оновлено результати

29.09.2026
  мін 15,00 · макс 14 968,90 · середньозважена 6 560,60 грн/МВт·год

26.09.2026 (перераховано)
  мін ... · макс ... · середньозважена ...
```

- Дані беруться з `get_daily(min(changed), max(changed))` і фільтруються до змінених діб.
- Числа у форматі `uk-UA`, як в UI (нерозривний пробіл, кома).
- Доби за зростанням дати.
- Якщо змінено понад 10 діб (масовий перерахунок), показано перші 10 і рядок «…і ще N діб».
  Так повідомлення не перевищить ліміт Telegram у 4096 символів.
- `price_weighted = null` (нульовий обсяг) показується як «—».

### Отримувачі і CLI

```
python -m app.notify recipients list
python -m app.notify recipients add <chat_id>      # ціле або @name; повтор — без дубліката
python -m app.notify recipients remove <chat_id>
python -m app.notify test                          # тестове повідомлення кожному ввімкненому
```

Валідація `chat_id`: `^-?\d+$` або `^@[A-Za-z][A-Za-z0-9_]{4,}$`. `test` друкує рядок на кожного
отримувача (`OK` або текст помилки без токена) і завершується з кодом 1, якщо бодай одна
доставка не вдалась. Без токена одразу пише «TELEGRAM_BOT_TOKEN не задано» і завершується з
кодом 2. Тестові повідомлення в журнал доставок не пишуться, бо не прив'язані до запуску.

### Модулі

```
app/notify/telegram.py     TelegramClient.send(chat_id, text) + redact
app/notify/message.py      build_message(daily, recalculated) — чиста функція
app/notify/recipients.py   RecipientRepository (list/add/remove/enabled)
app/notify/notifier.py     Notifier.notify_run(run_id, changed, recalculated)
app/notify/__main__.py     CLI recipients / test
app/storage/models.py      + TelegramRecipient, NotificationDelivery
alembic/versions/0003_telegram.py
```

## Risks / Trade-offs

- **`pending` після загибелі процесу** → повідомлення не надійде, але його видно в БД. Ручне
  дорозсилання можна додати пізніше, а дубль видалити неможливо.
- **Розсилка всередині блокування подовжує його на кілька секунд** → лише при `success`, тобто
  раз на добу. Паралельний запуск отримає `skipped_locked`, і це нормально.
- **Масовий перерахунок історії ОРЕЕ** → повідомлення обрізається до 10 діб, решта в UI.
- **`@channel` потребує, щоб бот був адміністратором каналу** → це обмеження Telegram, а не
  наше; `test` покаже помилку 400/403.
- **Живе тестування потребує справжнього бота** → автотести обходяться `MockTransport`, а ручна
  перевірка потребує токена й `chat_id` від користувача.

## Migration Plan

Міграція `0003` додає дві таблиці, відкат їх видаляє. Наявні дані не зачіпаються. Розгортання:
`alembic upgrade head`, `TELEGRAM_BOT_TOKEN` у `.env`, `python -m app.notify recipients add
<chat_id>`, перезапустити API.

## Open Questions

Немає.
