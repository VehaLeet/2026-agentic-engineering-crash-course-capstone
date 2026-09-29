## 1. Вимикач сповіщень: схема і сховище

- [x] 1.1 Колонка `AppSettings.notifications_enabled` і міграція `0005_notifications_enabled`;
      перевірка: `alembic upgrade head` на dev-БД проходить, `alembic check` без розбіжностей,
      `downgrade -1` і знову `upgrade head` проходять, наявний рядок має `notifications_enabled = true`.
- [x] 1.2 `NotificationSettingsStore.enabled()` / `set_enabled()` в `app/settings.py`; перевірка:
      тести стверджують `true` на порожній таблиці (самолікування), збереження `false` між новими
      екземплярами сховища і те, що зміна вимикача не чіпає налаштувань розкладу.

## 2. Розсилка з урахуванням вимикача

- [x] 2.1 `Notifier._notify` перевіряє вимикач до `_claim`; перевірка: тест із двома отримувачами і
      вимкненими сповіщеннями стверджує нуль звернень до Telegram, нуль доставок і статус запуску
      `success`.
- [x] 2.2 Без дорозсилання; перевірка: тест завершує запуск `success` із вимкненими сповіщеннями,
      вмикає їх і стверджує, що доставок для того запуску так і немає; наступний запуск `success`
      сповіщає як звичайно.

## 3. Отримувачі

- [x] 3.1 `RecipientRepository.get` і `set_enabled` (`UPDATE ... RETURNING`); перевірка: тести на
      вимкнення, повторне ввімкнення, `None` для невідомого `chat_id` і те, що вимкнений отримувач
      зникає з `enabled()`.

## 4. Клієнт Bot API

- [x] 4.1 Спільний `_call(method, body)` і `send` поверх нього; перевірка: наявні тести
      `test_client.py` і `test_notifier.py` зелені без змін.
- [x] 4.2 `get_updates()` з `timeout: 0`, `limit: 100`, без `offset` і `allowed_updates`; перевірка:
      тест на `MockTransport` стверджує URL `/bot<token>/getUpdates`, тіло запиту без `offset` і
      `allowed_updates`, повернений `result`; тест на 409 про webhook стверджує `TelegramError` після
      однієї спроби з описом Telegram і без токена.
- [x] 4.3 Перенести `TEST_TEXT` у `app/notify/message.py`; перевірка: `test_notify_cli.py` зелений.

## 5. Розбір кандидатів

- [x] 5.1 `candidates_from_updates` (`app/notify/candidates.py`); перевірка: тести на JSON у форматі
      Telegram стверджують: приватний чат `/start` → `private`, назва з `first_name`/`last_name`,
      `username`; канал через `my_chat_member` (`administrator`) і `channel_post` → `channel` з
      `title`; три повідомлення з одного чату дають один запис з останнім `last_seen_at` у UTC.
- [x] 5.2 Вибуття і шум; перевірка: тести стверджують, що група з останнім `my_chat_member`
      `left` чи `kicked` і приватний чат зі статусом `kicked` відсутні; група, куди бота видалили й
      додали знову, присутня; невідомі типи оновлень ігноруються; порожній список дає `[]`;
      сортування від найновішого.

## 6. Telegram-клієнт у застосунку

- [x] 6.1 `create_app(..., telegram=UNSET)`, `app.state.telegram` і нотифікатор із того самого
      клієнта; перевірка: наявні тести API і планувальника зелені, тест стверджує, що з
      `telegram=None` у лог пишеться попередження про відсутній токен, а збір працює.

## 7. API налаштувань (`app/api/telegram_routes.py`)

- [x] 7.1 `GET/PUT /settings/notifications`; перевірка: тести стверджують типове
      `{"enabled": true, "token_configured": true}`, `token_configured: false` з `telegram=None`,
      збереження `false` в новому екземплярі застосунку (імітація рестарту) і 422 без зміни
      вимикача для `{"enabled": "false"}` і `{}`; тіло відповіді не містить токена.
- [x] 7.2 `GET` і `POST /settings/telegram/recipients`; перевірка: тести стверджують порядок
      додавання, `[]` для порожнього переліку, 201 для нового, 200 з `enabled: false` для повторного
      додавання вимкненого (без дубліката), 422 для `"hello world"` і тіла без `chat_id`, і те, що
      доданий через API отримувач видно в CLI `recipients list`.
- [x] 7.3 `PATCH` і `DELETE /settings/telegram/recipients/{chat_id}`; перевірка: тести на вимкнення,
      `@oree_dam` у шляху, 404 для невідомого, 422 для `{"enabled": "no"}` без зміни стану, 204 при
      видаленні і збережену доставку `sent` після видалення отримувача.
- [x] 7.4 `POST /settings/telegram/recipients/{chat_id}/test`; перевірка: тести з підставним Bot API
      стверджують `{"ok": true}` і текст `TEST_TEXT`; `ok: false` з текстом 403 без токена; відправку
      вимкненому отримувачу і при вимкнених сповіщеннях; 404 без звернення до Telegram; 409 з
      `telegram=None`; відсутність нових рядків у `notification_deliveries`.
- [x] 7.5 `GET /settings/telegram/candidates`; перевірка: тести з підставним Bot API стверджують
      перелік із `added: true` для отримувача за id і для каналу, доданого як `@username`, і
      `added: false` для решти; два запити поспіль повертають те саме і не викликають `sendMessage`;
      409 з `telegram=None`; 502 з текстом без токена на 409 від Telegram і на постійний мережевий збій.
- [x] 7.6 Оновити перелік маршрутів у `test_no_route_requires_credentials`; перевірка: увесь
      `pytest` зелений.

## 8. Документація і приймання

- [x] 8.1 `docs/roadmap.md`: зріз 9 «виконано» з тим, що доведено; перевірка: рядок таблиці
      оновлено, а в «Боргах» записано обмеження кандидатів (24 години, 100 оновлень).
- [x] 8.2 Ручна перевірка з реальним ботом (кроки, що надсилають повідомлення, виконуються лише з
      дозволу власника): власник пише боту `/start`, `GET /settings/telegram/candidates` показує його
      чат; `POST` цього `chat_id` у отримувачі, потім `/test` отримує `{"ok": true}` і повідомлення
      приходить; `openspec validate add-settings-api --strict` проходить.
