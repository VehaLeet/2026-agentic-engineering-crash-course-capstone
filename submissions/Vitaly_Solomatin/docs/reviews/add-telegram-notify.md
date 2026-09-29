# Рев'ю: add-telegram-notify (capability `telegram-notify`), діапазон `1519460^..HEAD`, лише `backend/app/notify/` і тести до нього

Стан набору тестів: `make check-backend` зелений, 281 passed.

## Знахідки

### 1. У доставці зі станом `failed` записується максимум спроб, а не фактична кількість
- **file**: `/Users/vi/Desktop/AECCC_project/2026-agentic-engineering-crash-course-capstone/submissions/Vitaly_Solomatin/backend/app/notify/notifier.py`, **line**: 59
- **severity**: major
- **spec**: «Бот заблоковано отримувачем»: «доставка першому має стан `failed` після однієї спроби з текстом помилки». Також вимога «зберігати доставку… з кількістю спроб».
- **evidence**: На помилку записується `await self._finish(run_id, chat_id, "failed", self.client.attempts, str(e))`. `self.client.attempts` — це налаштований максимум (3, `telegram.py:21`), а не лічильник виконаних спроб. `TelegramError` не несе кількості спроб, тому 403, який не повторюється (`telegram.py:75`), потрапляє в журнал як `attempts=3`. Тест `test_one_recipient_failure_does_not_stop_others` розпаковує `a1` (`tests/test_notifier.py:83`), але ніде його не перевіряє, тому дефект не ловиться.
- **suggestion**: Передавати фактичну кількість спроб у `TelegramError`, наприклад атрибутом `attempts`, і записувати саме її. Тест: у `tests/test_notifier.py:84` додати `assert a1 == 1`, для 403 він зараз впаде з `3 != 1`.

### 2. Повтор після `ReadTimeout` або 5xx може надіслати дубль, хоча мета — «не більше одного»
- **file**: `/Users/vi/Desktop/AECCC_project/2026-agentic-engineering-crash-course-capstone/submissions/Vitaly_Solomatin/backend/app/notify/telegram.py`, **line**: 60
- **severity**: major
- **confidence**: medium. Поведінку прямо вимагає вимога «Надійність відправки», тож це суперечність усередині специфікації, а не лише в коді.
- **spec**: Purpose: «рівно один раз на кожне оновлення, без повторів». `design.md`: «дубль у Telegram гірший за пропуск».
- **evidence**: `except httpx.TransportError as e:  # мережа, таймаут` повторює `sendMessage` на будь-яку транспортну помилку, зокрема `ReadTimeout` і `RemoteProtocolError`. Вони виникають уже після того, як запит пішов, і Telegram міг його обробити. Так само 502/504 від шлюзу (рядок 70) не гарантують, що повідомлення не доставлено. Рядок `pending` у `notification_deliveries` захищає лише від повторного запуску, а не від повторів усередині `_call`. У підсумку отримувач може дістати два однакові повідомлення.
- **suggestion**: Для `sendMessage` повторювати лише помилки, після яких запит точно не відправлено: `ConnectError`, `ConnectTimeout`, `PoolTimeout`, а також 429. `ReadTimeout` і 5xx записувати як `failed` або узгодити це в специфікації окремим рішенням. Тест: `MockTransport` записує запит і кидає `httpx.ReadTimeout`, очікується рівно один запит.

### 3. Після понад 10 змінених діб повідомлення ховає найновіші, зокрема щойно опубліковану
- **file**: `/Users/vi/Desktop/AECCC_project/2026-agentic-engineering-crash-course-capstone/submissions/Vitaly_Solomatin/backend/app/notify/message.py`, **line**: 29
- **severity**: major
- **spec**: «Для кожної зміненої доби постачання воно MUST містити дату, мінімальну й максимальну ціну та середньозважену…». Обрізання описане лише в `design.md`, у специфікації його немає.
- **evidence**: `days = sorted(daily, key=lambda x: x.delivery_date)`, далі `for d in days[:MAX_DAYS]:` бере 10 найстаріших діб. Якщо ОРЕЕ перерахує понад 10 діб разом із публікацією нової доби, нова доба (найпізніша дата) опиниться в «…і ще N діб» без цін. Саме її отримувач найбільше хоче побачити. До того ж це поведінка, якої немає в специфікації.
- **suggestion**: При обрізанні ставити першими нові (неперераховані) доби або найпізніші дати. Обрізання разом із пріоритетом треба описати сценарієм у `spec.md`. Тест: 12 перерахованих діб і одна нова, очікується, що дата нової доби є в тексті.

### 4. Будь-який виняток, крім `TelegramError`, перериває розсилку решті отримувачів і лишає `pending`
- **file**: `/Users/vi/Desktop/AECCC_project/2026-agentic-engineering-crash-course-capstone/submissions/Vitaly_Solomatin/backend/app/notify/notifier.py`, **line**: 58
- **severity**: minor
- **confidence**: low-medium
- **spec**: «Збій доставки одному отримувачу MUST NOT зривати доставку іншим».
- **evidence**: У циклі перехоплюється лише `except TelegramError as e:`. Інші винятки з `send()` виходять із циклу до `notify_run` і там лише логуються, тож отримувачі далі в переліку не отримують нічого, а поточна доставка лишається `pending`. Приклади: `httpx.DecodingError` (це `RequestError`, а не `TransportError`), `ValueError` з `float(retry_after)` на `telegram.py:73`, `AttributeError`, якщо `parameters` не є словником.
- **suggestion**: У `telegram.py` загортати всі `httpx.HTTPError` і помилки розбору відповіді в `TelegramError`. Або в циклі перехоплювати `Exception` для конкретного отримувача, записувати `failed` і йти далі. Тест: транспорт для першого chat_id кидає `httpx.DecodingError`, очікується, що другий отримав повідомлення.

### 5. `retry_after` не обмежено, а сон триває всередині advisory lock
- **file**: `/Users/vi/Desktop/AECCC_project/2026-agentic-engineering-crash-course-capstone/submissions/Vitaly_Solomatin/backend/app/notify/telegram.py`, **line**: 73
- **severity**: minor
- **spec**: — (AGENTS.md: записувачі беруть спільний advisory lock, конкурент отримує `skipped_locked`)
- **evidence**: `await self.sleep(float(retry_after) if retry_after else 2 ** (attempt - 1))` чекає стільки, скільки скаже Telegram, без верхньої межі. `notify_run` викликається всередині `dam_writer_lock` (`app/collection/collect.py:75-78`). Великий `retry_after`, помножений на кількість отримувачів, тримає блокування весь цей час, і плановий та ручний збори завершуються `skipped_locked`.
- **suggestion**: Обмежити очікування, наприклад до 30 с. Якщо `retry_after` більший, одразу завершувати доставку як `failed`. Тест: 429 з `retry_after=3600`, очікується `TelegramError` без виклику `sleep(3600)`.

### 6. Тест «Повторне ввімкнення без дорозсилання» нічого не доводить
- **file**: `/Users/vi/Desktop/AECCC_project/2026-agentic-engineering-crash-course-capstone/submissions/Vitaly_Solomatin/backend/tests/test_notifier.py`, **line**: 177
- **severity**: minor
- **spec**: «Повторне ввімкнення без дорозсилання».
- **evidence**: `await notifier.notify_run(missed.run_id, [])` передає порожній `changed`, тож `_notify` завершується на першій же перевірці `not changed` (`notifier.py:43`), хай яким був би вимикач. Наступні рядки 179-181 перевіряють лише, що обидва отримувачі щось отримали, а не що в тексті немає діб пропущеного запуску (01.07 і 02.07).
- **suggestion**: Після ввімкнення перевірити текст наступного повідомлення: `"01.07.2026" not in text and "02.07.2026" not in text`. Виклик на рядку 177 прибрати або передати справжні `missed.changed_days`, якщо саме це мали на увазі.

### 7. Валідація `chat_id` пропускає Unicode-цифри
- **file**: `/Users/vi/Desktop/AECCC_project/2026-agentic-engineering-crash-course-capstone/submissions/Vitaly_Solomatin/backend/app/notify/recipients.py`, **line**: 13
- **severity**: minor
- **confidence**: low
- **spec**: «Ідентифікатор чату MUST бути цілим числом… Некоректний ідентифікатор MUST відхилятися».
- **evidence**: `_CHAT_ID = re.compile(r"^(-?\d+|@[A-Za-z][A-Za-z0-9_]{4,})$")` задано без `re.ASCII`, тому для `str` `\d` збігається з будь-якою десятковою Unicode-цифрою. Рядок `"١٢٣"` (арабсько-індійські цифри) буде прийнято й збережено, хоча Telegram його відхилить.
- **suggestion**: Додати `re.ASCII` або замінити `\d` на `[0-9]`. Тест: додати `"١٢٣"` у параметри `test_invalid_chat_ids`.

### 8. Новий `httpx.AsyncClient` на кожен виклик Bot API
- **file**: `/Users/vi/Desktop/AECCC_project/2026-agentic-engineering-crash-course-capstone/submissions/Vitaly_Solomatin/backend/app/notify/telegram.py`, **line**: 56
- **severity**: minor
- **spec**: —
- **evidence**: `async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:` створюється в `_call`, тобто окремо для кожного отримувача. Кожне повідомлення відкриває новий TCP- і TLS-з'єднання, і пул не перевикористовується. Функціонально це коректно, але суперечить рекомендації httpx перевикористовувати клієнт.
- **suggestion**: Тримати один клієнт на `TelegramClient` або на розсилку `_notify`, наприклад через `async with` навколо циклу, і закривати його після розсилки.

## Сценарії без тестів

Нижче сценарії, які покриті частково: тест є лише на рівні клієнта або репозиторію, а не на рівні доставки чи повного збору.
- «Тимчасовий збій Telegram: доставка має стан `sent` і дві спроби». Перевірено лише `send() == 2` (`tests/test_notify_parts.py:82`). Що запис у `notification_deliveries` має `attempts=2`, не перевіряється.
- «Бот заблоковано отримувачем… після однієї спроби». Кількість спроб у доставці не перевіряється (див. знахідку 1).
- «Токен не просочується в помилки: записаний у журнал доставок текст». Перевірено лише текст винятку клієнта (`tests/test_notify_parts.py:107`), а не `error_message` у `notification_deliveries`.
- «Збій доставки не змінює статусу запуску: усі доставки `failed`». Тести покривають виняток нотифікатора і збій одного з двох отримувачів, але не випадок, коли всі доставки `failed`.
- «Вимкнений отримувач: запуск `success`, повідомлення не надіслано». Перевірено лише `repo.enabled()` (`tests/test_notify_parts.py:41`), без повного збору.
- «Повторно ввімкнений отримувач отримав повідомлення». Перевірено лише на рівні репозиторію (`tests/test_notify_parts.py:141`), без повного збору.
- «Повторне ввімкнення без дорозсилання». Тест фактично нічого не перевіряє (див. знахідку 6).

## Підсумок

critical: 0, major: 3, minor: 5.
