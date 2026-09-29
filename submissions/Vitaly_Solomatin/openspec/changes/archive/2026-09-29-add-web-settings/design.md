## Context

- Фронтенд — одна сторінка без маршрутизації: `App.tsx` рендерить `StatusPanel` і `DataView`.
  Стан у Zustand-сторах (`state/*.ts`), виклики API — у `api/client.ts` через спільний
  `request()` з префіксом `/api` (проксі Vite на той самий origin).
- `request()` розрізняє лише мережу/5xx (`ApiUnavailable`), 422 (`ApiValidationError` із `detail`) і
  «решту» (`ApiContractError`). 404 і 409 з нових ендпойнтів зараз стали б «порушенням контракту».
- Тести: vitest + Testing Library; стори тестуються з `vi.mock('../api/client.ts')`, компоненти —
  з підставленим станом стора.
- Час за Києвом уже форматує `lib/time.ts::formatKyiv`.
- Контракти API: `openspec/specs/collection-schedule` і `openspec/specs/telegram-settings`.

## Goals / Non-Goals

**Goals:**
- Жодних нових залежностей: ні маршрутизатора, ні бібліотеки форм.
- Кожна дія в налаштуваннях має явні стани «триває / успіх / помилка», перевірені тестами стору.
- Вміст вкладки «Дані» не змінюється: наявні тести `StatusPanel` і `DataView` проходять без змін.

**Non-Goals:**
- Оптимістичні оновлення переліку отримувачів: після кожної дії показуємо стан, що повернув сервер.
- Синхронізація між кількома відкритими вкладками браузера.

## Decisions

### 1. Вкладки через `location.hash`

Хук `useTab()` читає `location.hash` (`#settings` → «Налаштування», інакше «Дані») і підписується на
`hashchange`. Перемикання — це присвоєння `location.hash`, тож «назад»/«вперед» і перезавантаження
працюють без власної історії. Кнопки вкладок мають `role="tab"` і `aria-selected`, контейнер —
`role="tablist"`.

Вкладка «Дані» рендерить `StatusPanel` і `DataView` як зараз. Перевірка з'єднання
(`useConnection.check`) лишається в `App`, тож не залежить від вкладки. Неактивна вкладка не
рендериться: графік ECharts на «Даних» перестворюється при поверненні, і це дешево (див. виміри
зрізу 10b).

*Альтернатива:* react-router. Відкинуто: дві вкладки не виправдовують нову залежність.

### 2. Клієнт API: `ApiRequestError` для 4xx

`request()` для 404 і 409 кидає `ApiRequestError(status, detail)`, де `detail` береться з тіла
FastAPI (`{"detail": "..."}`), якщо воно рядок. `ApiValidationError` лишається для 422, щоб не
чіпати наявних споживачів. Інші 4xx (зокрема 401) лишаються `ApiContractError`, як і вимагає наявний
тест: автентифікації немає, тож 401 — справді неочікувана відповідь. `request()` також навчиться:
- надсилати JSON-тіло (`json` у параметрах → `Content-Type: application/json`);
- приймати 204 без тіла (для `DELETE`).

Нові функції клієнта з перевіркою форми відповіді, як у наявних:

```
getSchedule(), putSchedule({enabled, interval_minutes})
getNotifications(), putNotifications({enabled})
listRecipients(), addRecipient(chat_id), setRecipientEnabled(chat_id, enabled),
deleteRecipient(chat_id), testRecipient(chat_id)
```

`chat_id` у шляху кодується `encodeURIComponent` (`@name`, від'ємні числа).

### 3. Один стор `state/settings.ts`

```
settings: {state: 'loading'} | {state: 'unavailable'} | {state: 'error', message}
        | {state: 'ok', schedule, notifications, recipients}
pending:  {schedule?: true, notifications?: true, recipients: Record<chat_id, 'toggle'|'delete'|'test'>, adding?: true}
feedback: {schedule?: Msg, notifications?: Msg, adding?: Msg, recipient: Record<chat_id, Msg>}
Msg = {kind: 'ok' | 'error' | 'warning', text}
```

Дії: `load`, `saveSchedule`, `setNotifications`, `addRecipient`, `toggleRecipient`,
`removeRecipient`, `testRecipient`. `load` запускається під час відкриття вкладки «Налаштування»
(`useEffect` у компоненті вкладки) і робить три запити паралельно.

- **Отримувачі після змін.** Після `add`, `toggle` і `remove` стор перечитує перелік з сервера. Так
  «повторне додавання не створює дубліката» і «404 на видалення прибирає рядок» виконуються
  природно, без логіки злиття на клієнті.
- **Вимикачі.** Сповіщення і перемикач отримувача показують нове значення лише після відповіді
  сервера; поки запит триває, контрол недоступний. «Повернення до попереднього значення» при
  помилці — це просто відсутність зміни стану.
- **Форма розкладу** тримає чернетку в локальному стані компонента. Валідація (ціле 5…1440)
  робиться там само, до надсилання. Межі — константи в `api/types.ts`, що повторюють бекенд.

### 4. Тексти і повідомлення

- `ApiUnavailable` → «Backend недоступний» (як у `collect.ts`).
- `ApiValidationError` / `ApiRequestError` → `detail` сервера.
- 409 на тест («токен не задано») на практиці не виникає: кнопка недоступна, коли
  `token_configured === false`. Якщо все ж прийшов, показується `detail`.
- Тест з `ok: false` → `Msg{kind: 'warning'}` із текстом Telegram біля отримувача, без `role="alert"`
  для всієї сторінки. Збій самого запиту → `Msg{kind: 'error'}`.
- Підтвердження видалення — `window.confirm`. У тестах його підміняють `vi.spyOn(window, 'confirm')`.

### 5. Компоненти

```
components/Tabs.tsx
components/settings/SettingsView.tsx       — завантаження, помилка, три секції
components/settings/ScheduleForm.tsx
components/settings/NotificationsToggle.tsx
components/settings/RecipientsList.tsx     — перелік, форма додавання, тест
```

Стилі — наявні класи `.card`, `.muted`, кнопки; нові класи лише для рядка отримувача, повідомлень
і вкладок, з кольорами з токенів теми.

## Risks / Trade-offs

- [Тест отримувача триває до ~35 с при недоступному Telegram] → кнопка показує «Надсилаємо…»,
  решта сторінки працює.
- [`window.confirm` — нативний діалог, не в стилі теми] → прийнятно для внутрішнього інструменту на
  1–5 людей; власний діалог можна зробити пізніше.
- [Межі інтервалу продубльовані у фронтенді] → сервер однаково валідує, і його 422 показується
  користувачу. Розбіжність меж проявиться помилкою, а не збереженням невалідного значення.
- [Перечитування переліку після кожної дії — зайвий запит] → перелік крихітний; зате немає
  розбіжностей між клієнтом і сервером.
