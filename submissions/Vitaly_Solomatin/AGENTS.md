# AGENTS.md

OREE DAM Monitor: внутрішній сервіс, який сам завантажує результати РДН з ОРЕЕ, зберігає їх у
Postgres, показує графік і таблицю цін і надсилає сповіщення в Telegram. Продукт описано в
`docs/brief.md`, порядок робіт — у `docs/roadmap.md`, поведінку системи — в `openspec/specs/`.

## Структура

- `backend/`: Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, APScheduler, httpx.
  - `app/dam_source/`: завантаження і розбір CSV.
  - `app/storage/`: моделі й репозиторій.
  - `app/collection/`: збір, журнал запусків, advisory lock.
  - `app/notify/`: Telegram.
  - `app/api/`: HTTP.
- `frontend/`: React, TypeScript, Vite, ECharts, Zustand.
  - Стори в `src/state/`, виклики API в `src/api/`.
- `docker-compose.yml` і `Makefile`: увесь стек однією командою.

## Команди

```sh
make up | down | logs | backfill | clean          # увесь стек у Docker (UI http://127.0.0.1:8080)
make check                                        # усі перевірки: хуки, backend, frontend, lint, build
make check-hooks | check-backend | check-frontend # те саме частинами
docker compose up -d postgres                     # лише БД для розробки
cd backend  && uv run python -m app.api           # API на 127.0.0.1:8000
cd frontend && npm run dev                        # UI на :5173, /api проксується на :8000
```

Під час роботи запускай перевірку тієї частини, яку змінюєш (`make check-backend` тощо).
Перш ніж казати «готово», запусти `make check`: «готово» означає, що він зелений.

## Як вносити зміни

- Кожна фіча проходить через OpenSpec: `/opsx:propose`, потім `/opsx:apply`, потім `/opsx:archive`.
  Контекст і правила — в `openspec/config.yaml`.
- Одна зміна = один вертикальний зріз, який можна переглянути за 15 хвилин.
- Під час propose нічого не реалізуй. Під час apply не виходь за межі `tasks.md`: якщо задача
  вимагає більшого, зупинись і спитай.
- Нову зміну додавай у `docs/roadmap.md`. Номери зрізів стабільні: коли зріз ділиться, частини
  отримують літери (11b, 11c).
- Артефакти, коментарі в коді й повідомлення комітів пиши українською, стилем сусіднього коду.
  Коміти — короткий заголовок без трейлерів, лише коли просять, без push.

## Інваріанти

- Секрети лише в env (`TELEGRAM_BOT_TOKEN`, `DATABASE_URL`). Налаштування — в БД (`app_settings`).
- Числа — `Decimal`, не `float`. Період доби — номер 1..25 як у джерелі, без конвертації в годину.
- Upsert за ключем (дата постачання, період). Зміни визначаються хешем кожної доби.
- Записувачі результатів РДН (збір, бекфіл) беруть спільний advisory lock. Хто не отримав
  блокування, завершується зі статусом `skipped_locked` і не чекає.
- Сервіс без автентифікації, тож доступний лише з localhost: API слухає loopback, а всі порти
  compose прив'язані до `127.0.0.1`. Не відкривай сервіс у мережу.
- API працює в одному процесі з одним воркером: планувальник живе в пам'яті процесу API.

## Питай дозволу щоразу

- Перед кожною зміною `.claude/settings.json`, `backend/pyproject.toml` і `frontend/package.json`.
- Перед `make clean`, `docker compose down -v` і `alembic downgrade`: dev-запуск і Docker-стек
  ділять один том БД.

## Ніколи

- Не чіпай `.env*`, окрім `.env.example`. Хук однаково це заблокує.
- Не видаляй тести і не вимикай правила лінтера, щоб отримати зелений результат.
- Не виконуй `git push --force`.
- Не виконуй `rm -rf`.

## Що ще блокують хуки в `.claude/hooks/`

- `os.environ` / `os.getenv` у `backend/app/api/**`. Виняток — лаунчер `__main__.py`.
- Звернення до Telegram Bot API: напряму, через ендпойнти `/settings/telegram/candidates` і
  `.../test` або через `app.notify test`. Такі перевірки робить власник вручну.
- Читання сирого `.agent-log/actions.jsonl`. Для цього є `node scripts/agent-log-summary.mjs`.
- Shell-скрипти, у тексті яких є рядки з заборон про Telegram, навіть якщо скрипт лише пише код.
  Такий код змінюй інструментами Edit і Write.
