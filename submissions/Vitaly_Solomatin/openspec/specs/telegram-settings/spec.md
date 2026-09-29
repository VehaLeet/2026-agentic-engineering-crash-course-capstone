# telegram-settings Specification

## Purpose

Керування Telegram-сповіщеннями через HTTP API: хто отримує повідомлення, як знайти `chat_id`
нового отримувача без сторонніх інструментів, як перевірити доставку і як вимкнути сповіщення
цілком.

## Requirements

### Requirement: Перелік отримувачів

`GET /settings/telegram/recipients` SHALL повертати код 200 і перелік отримувачів у порядку
додавання. Кожен елемент MUST містити `chat_id` (рядок) і `enabled` (булеве). Порожній перелік
MUST повертатися як порожній масив.

#### Scenario: Два отримувачі

- **GIVEN** додано отримувачів `123456789` і `-1001234567890`, другий вимкнено
- **WHEN** запитується `GET /settings/telegram/recipients`
- **THEN** відповідь має код 200 і тіло
  `[{"chat_id": "123456789", "enabled": true}, {"chat_id": "-1001234567890", "enabled": false}]`

#### Scenario: Отримувачів немає

- **GIVEN** жодного отримувача не додано
- **WHEN** запитується `GET /settings/telegram/recipients`
- **THEN** відповідь має код 200 і тіло `[]`

### Requirement: Додавання отримувача

`POST /settings/telegram/recipients` з тілом `{"chat_id": <рядок>}` SHALL додавати увімкненого
отримувача і відповідати кодом 201 з доданим отримувачем. Якщо отримувач із таким `chat_id` уже є,
відповідь MUST мати код 200 і поточний стан наявного отримувача, без дубліката і без зміни його
ознаки `enabled`. Ідентифікатор MUST проходити ту саму перевірку, що й у команді додавання:
ціле число (зокрема від'ємне) або `@name`. Некоректний ідентифікатор або тіло без `chat_id` MUST
відхилятися з кодом 422 без зміни переліку.

#### Scenario: Новий отримувач

- **GIVEN** перелік отримувачів порожній
- **WHEN** надходить `POST /settings/telegram/recipients` з `{"chat_id": "123456789"}`
- **THEN** відповідь має код 201 і тіло `{"chat_id": "123456789", "enabled": true}`

#### Scenario: Повторне додавання вимкненого отримувача

- **GIVEN** отримувач `123456789` уже є і вимкнений
- **WHEN** надходить `POST /settings/telegram/recipients` з `{"chat_id": "123456789"}`
- **THEN** відповідь має код 200 і тіло `{"chat_id": "123456789", "enabled": false}`
- **AND** у переліку лишається один такий отримувач

#### Scenario: Некоректний ідентифікатор

- **GIVEN** застосунок запущено
- **WHEN** надходить `POST /settings/telegram/recipients` з `{"chat_id": "hello world"}`
- **THEN** відповідь має код 422 з поясненням, що очікується ціле число або `@channel`
- **AND** перелік отримувачів не змінився

### Requirement: Увімкнення і вимкнення отримувача

`PATCH /settings/telegram/recipients/{chat_id}` з тілом `{"enabled": <булеве>}` SHALL змінювати
ознаку отримувача і повертати код 200 з його новим станом. Для невідомого `chat_id` MUST
повертатися код 404. Тіло без `enabled` або з небулевим значенням MUST відхилятися з кодом 422.

#### Scenario: Вимкнення

- **GIVEN** увімкнений отримувач `123456789`
- **WHEN** надходить `PATCH /settings/telegram/recipients/123456789` з `{"enabled": false}`
- **THEN** відповідь має код 200 і тіло `{"chat_id": "123456789", "enabled": false}`

#### Scenario: Отримувач-канал

- **GIVEN** увімкнений отримувач `@oree_dam`
- **WHEN** надходить `PATCH /settings/telegram/recipients/@oree_dam` з `{"enabled": false}`
- **THEN** відповідь має код 200 і отримувач вимкнений

#### Scenario: Невідомий отримувач

- **GIVEN** отримувача `555` немає
- **WHEN** надходить `PATCH /settings/telegram/recipients/555` з `{"enabled": true}`
- **THEN** відповідь має код 404

#### Scenario: Небулеве значення

- **GIVEN** отримувач `123456789` увімкнений
- **WHEN** надходить `PATCH /settings/telegram/recipients/123456789` з `{"enabled": "no"}`
- **THEN** відповідь має код 422
- **AND** отримувач лишається увімкненим

### Requirement: Видалення отримувача

`DELETE /settings/telegram/recipients/{chat_id}` SHALL видаляти отримувача і відповідати кодом
204. Для невідомого `chat_id` MUST повертатися код 404. Видалення MUST NOT стирати історію доставок
цьому отримувачу.

#### Scenario: Видалення з історією доставок

- **GIVEN** отримувач `123456789`, якому вже була доставка зі станом `sent`
- **WHEN** надходить `DELETE /settings/telegram/recipients/123456789`
- **THEN** відповідь має код 204
- **AND** отримувача немає в переліку
- **AND** доставка зі станом `sent` лишилась у журналі доставок

#### Scenario: Невідомий отримувач

- **GIVEN** отримувача `555` немає
- **WHEN** надходить `DELETE /settings/telegram/recipients/555`
- **THEN** відповідь має код 404

### Requirement: Кандидати в отримувачі

`GET /settings/telegram/candidates` SHALL на кожен запит читати оновлення бота, які Telegram ще
зберігає, і повертати код 200 з переліком чатів, що написали боту, опублікували повідомлення в
каналі з ботом або додали бота в групу чи канал. Кожен чат MUST з'являтися один раз і містити
`chat_id` (рядок), `type` (`private`, `group`, `supergroup` або `channel`), `title` (назва групи чи
каналу або ім'я людини), `username` (або `null`), `last_seen_at` (час останнього оновлення від
цього чату) і `added` (чи є вже отримувач із таким `chat_id`). Перелік MUST бути впорядкований від
найновішого. Чат, у якому останнє оновлення показує, що бота видалено, вигнано або заблоковано,
MUST NOT потрапляти в перелік.

Читання MUST NOT підтверджувати оновлення в Telegram і MUST NOT надсилати жодних повідомлень:
повторний запит бачить ті самі чати. Без токена бота відповідь MUST мати код 409 з поясненням, що
токен не задано. Збій Telegram (мережа, відповідь з помилкою, налаштований webhook) MUST давати
код 502 з текстом помилки без токена.

#### Scenario: Людина натиснула Start

- **GIVEN** користувач `@olena` (id `987654321`) надіслав боту `/start`
- **WHEN** запитується `GET /settings/telegram/candidates`
- **THEN** перелік містить `{"chat_id": "987654321", "type": "private", "title": "Олена",
  "username": "olena", "added": false}` з часом повідомлення в `last_seen_at`

#### Scenario: Бота додали в канал

- **GIVEN** бота призначено адміністратором каналу «Ціни РДН» з id `-1001234567890`
- **WHEN** запитується `GET /settings/telegram/candidates`
- **THEN** перелік містить чат `-1001234567890` з типом `channel` і назвою «Ціни РДН»

#### Scenario: Кілька повідомлень з одного чату

- **GIVEN** той самий користувач написав боту тричі
- **WHEN** запитується `GET /settings/telegram/candidates`
- **THEN** цей чат у переліку один раз, а `last_seen_at` — час останнього повідомлення

#### Scenario: Уже доданий отримувач

- **GIVEN** користувач `987654321` написав боту і вже є отримувачем
- **WHEN** запитується `GET /settings/telegram/candidates`
- **THEN** для цього чату `added` дорівнює `true`

#### Scenario: Бота видалили з групи

- **GIVEN** бота додали в групу, а пізніше видалили з неї
- **WHEN** запитується `GET /settings/telegram/candidates`
- **THEN** цієї групи в переліку немає

#### Scenario: Повторний запит

- **GIVEN** користувач написав боту, і кандидатів уже запитали один раз
- **WHEN** кандидатів запитують удруге
- **THEN** користувач знову є в переліку
- **AND** боту не надіслано жодного повідомлення

#### Scenario: Оновлень немає

- **GIVEN** боту ніхто не писав останні 24 години
- **WHEN** запитується `GET /settings/telegram/candidates`
- **THEN** відповідь має код 200 і тіло `[]`

#### Scenario: Токен не задано

- **GIVEN** `TELEGRAM_BOT_TOKEN` відсутній
- **WHEN** запитується `GET /settings/telegram/candidates`
- **THEN** відповідь має код 409 з поясненням, що токен не задано

#### Scenario: На бота налаштовано webhook

- **GIVEN** Telegram відповідає на читання оновлень помилкою 409 про активний webhook
- **WHEN** запитується `GET /settings/telegram/candidates`
- **THEN** відповідь має код 502 з текстом помилки Telegram
- **AND** текст помилки не містить токена

### Requirement: Тестове повідомлення отримувачу

`POST /settings/telegram/recipients/{chat_id}/test` SHALL надсилати наявному отримувачу тестове
повідомлення незалежно від його ознаки `enabled` і глобального вимикача сповіщень. Відповідь MUST
мати код 200 і тіло `{"ok": true}` при успіху або `{"ok": false, "error": <текст помилки Telegram>}`
при відмові Telegram. Текст помилки MUST NOT містити токена. Для невідомого `chat_id` MUST
повертатися код 404, а без токена бота — код 409. Тестове повідомлення MUST NOT потрапляти в журнал
доставок.

#### Scenario: Успішна перевірка

- **GIVEN** отримувач `123456789`, який натиснув Start у бота
- **WHEN** надходить `POST /settings/telegram/recipients/123456789/test`
- **THEN** відповідь має код 200 і тіло `{"ok": true}`
- **AND** отримувач отримав тестове повідомлення

#### Scenario: Людина ще не натиснула Start

- **GIVEN** отримувач `123456789`, для якого Telegram відповідає 403
  `Forbidden: bot can't initiate conversation with a user`
- **WHEN** надходить `POST /settings/telegram/recipients/123456789/test`
- **THEN** відповідь має код 200, `ok` дорівнює `false`, а `error` містить текст помилки Telegram

#### Scenario: Вимкнений отримувач

- **GIVEN** вимкнений отримувач `123456789`
- **WHEN** надходить `POST /settings/telegram/recipients/123456789/test`
- **THEN** тестове повідомлення надіслано

#### Scenario: Невідомий отримувач

- **GIVEN** отримувача `555` немає
- **WHEN** надходить `POST /settings/telegram/recipients/555/test`
- **THEN** відповідь має код 404
- **AND** жодного звернення до Telegram не зроблено

#### Scenario: Токен не задано

- **GIVEN** `TELEGRAM_BOT_TOKEN` відсутній, а отримувач `123456789` є
- **WHEN** надходить `POST /settings/telegram/recipients/123456789/test`
- **THEN** відповідь має код 409 з поясненням, що токен не задано

### Requirement: Глобальний вимикач сповіщень

`GET /settings/notifications` SHALL повертати код 200 і тіло з полями `enabled` (глобальний
вимикач, типово `true`) і `token_configured` (чи задано `TELEGRAM_BOT_TOKEN`). Відповідь MUST NOT
містити токена чи будь-якої його частини. `PUT /settings/notifications` з тілом
`{"enabled": <булеве>}` SHALL зберігати вимикач у БД і повертати код 200 з тілом, як у GET. Тіло
без `enabled` або з небулевим значенням MUST відхилятися з кодом 422 без зміни вимикача. Вимикач
MUST переживати рестарт процесу.

#### Scenario: Типовий стан

- **GIVEN** БД щойно створено міграціями, а токен задано
- **WHEN** запитується `GET /settings/notifications`
- **THEN** відповідь має код 200 і тіло `{"enabled": true, "token_configured": true}`

#### Scenario: Вимкнення

- **GIVEN** сповіщення увімкнено
- **WHEN** надходить `PUT /settings/notifications` з `{"enabled": false}`
- **THEN** відповідь має код 200 і `enabled` дорівнює `false`
- **AND** після рестарту процесу `enabled` лишається `false`

#### Scenario: Токен не задано

- **GIVEN** `TELEGRAM_BOT_TOKEN` відсутній
- **WHEN** запитується `GET /settings/notifications`
- **THEN** `token_configured` дорівнює `false`

#### Scenario: Некоректне тіло

- **GIVEN** сповіщення увімкнено
- **WHEN** надходить `PUT /settings/notifications` з `{"enabled": "false"}` або без поля `enabled`
- **THEN** відповідь має код 422
- **AND** сповіщення лишаються увімкненими
