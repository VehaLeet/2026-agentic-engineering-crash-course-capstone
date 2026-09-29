## Context

- Контракт: `GET /settings/telegram/candidates` → масив `{chat_id, type, title, username,
  last_seen_at, added}`; 409 без токена, 502 при збої Telegram (`openspec/specs/telegram-settings`).
- `api/client.ts` уже має `request()`, `checked()` і `ApiRequestError` для 404/409; 502 стає
  `ApiUnavailable` («Backend недоступний»), бо `request()` вважає будь-який 5xx недоступністю.
- Стор `state/settings.ts` уже має `addRecipient`, що перечитує перелік отримувачів.
- `RecipientsList` знає `tokenConfigured`.

## Goals / Non-Goals

**Goals:**
- Жодних змін у поведінці наявних секцій; кандидати — окремий блок усередині секції отримувачів.
- Позначка «вже додано» завжди відповідає серверу, а не локальним здогадкам.

**Non-Goals:**
- Кешування кандидатів між відкриттями вкладки.

## Decisions

### 1. Текст помилки 502

Зараз `request()` перетворює будь-який 5xx на `ApiUnavailable` без тексту сервера, а специфікація
вимагає показати текст помилки Telegram (наприклад, про webhook). Тому для 502 `request()` читатиме
`detail` з тіла: якщо це рядок, повідомлення `ApiUnavailable` стане цим текстом, і стор показуватиме
його замість загального «Backend недоступний». Коли 502 приходить від проксі Vite (backend не
запущено), тіла з `detail` немає, і лишається загальний текст. Тип помилки не змінюється, тож
наявна логіка з'єднання (`connection.ts`) працює, як раніше.

*Альтернатива:* окремий тип `ApiUpstreamError`. Відкинуто: тоді `useConnection` і `collect.ts`
довелося б навчити ще одного типу без реальної користі.

### 2. Стан кандидатів у сторі налаштувань

```
candidates: {state: 'idle'} | {state: 'loading'} | {state: 'ok', items: Candidate[]} | {state: 'error', message}
findCandidates(): Promise<void>
addCandidate(chatId): Promise<void>   // addRecipient + повторний findCandidates для позначок added
```

Після додавання кандидати перезапитуються, бо `added` рахує сервер (зокрема для каналів,
доданих як `@username`). `load()` скидає кандидатів у `idle`, тож запиту без натискання немає.
Помилка додавання кандидата показується тим самим `feedback.adding`, що й ручне додавання.

### 3. Відображення

Компонент `components/settings/Candidates.tsx` під формою ручного додавання. Тип перекладається:
`private` → «особистий чат», `group`/`supergroup` → «група», `channel` → «канал», інше — як є.
Час — `formatKyiv(last_seen_at)`. Порожній результат пояснює обмеження 24 годин.

## Risks / Trade-offs

- [Кандидати застаріють після додавання отримувача деінде] → позначки оновлюються після кожного
  додавання з UI і повторного натискання «Знайти чати».
- [Зміна повідомлення `ApiUnavailable` для 502 з `detail`] → зачіпає лише відповіді, де бекенд
  явно повернув `detail`; наявні тести клієнта мають лишитися зеленими.
