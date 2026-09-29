## Context

- `docker-compose.yml` зараз має лише `postgres` (`image: ${POSTGRES_IMAGE}`, порт
  `127.0.0.1:5432:5432`, healthcheck `pg_isready`). Тест `test_image_tag_shared_by_compose_and_fixture`
  вимагає, щоб сервіс `postgres` лишився з цим рядком образу.
- API запускається `python -m app.api`: запускач читає `API_HOST`/`API_PORT`, відмовляє для
  не-loopback адрес (`resolve_host`) і стартує uvicorn з одним воркером. Планувальник живе в
  процесі API.
- Міграції — Alembic, URL з `DATABASE_URL` (`app/storage/database.py`).
- Фронтенд звертається до `/api/...`; у dev Vite проксує `/api` на backend, **відрізаючи префікс**.
  Вкладки працюють через hash, тож SPA-маршрутизації на сервері не потрібно.
- `.env` не в git; `.env.example` містить `POSTGRES_IMAGE`, `DATABASE_URL` (localhost) і закоментовані
  змінні.

## Goals / Non-Goals

**Goals:**
- Dev-сценарій не ламається: `docker compose up -d postgres` + `uv run` + `npm run dev` працюють
  як раніше.
- Образи маленькі й відтворювані: залежності з `uv.lock` і `package-lock.json`.

**Non-Goals:**
- Налаштування продуктивності nginx (кешування, gzip) — сторінка внутрішня.
- Кілька середовищ (dev/prod compose-файли).

## Decisions

### 1. Режим контейнера в запускачі

`resolve_host(value, in_container)`: коли `API_IN_CONTAINER=1`, додатково дозволяється рівно
`0.0.0.0`. «Справді в контейнері» перевіряється наявністю `/.dockerenv` (Docker) або
`/run/.containerenv` (Podman). Якщо змінна задана, а маркерів немає — помилка конфігурації з
поясненням. Так випадково скопійований на хост `API_IN_CONTAINER=1` не відкриє API в мережу.
Функція перевірки маркерів приймає шляхи параметром, щоб тести не залежали від середовища.

*Альтернатива:* запускати `uvicorn --host 0.0.0.0` напряму в образі. Відкинуто власником: перевірка
межі в контейнері зникла б мовчки.

### 2. Образ backend

```
FROM ghcr.io/astral-sh/uv:<версія> AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./ ; COPY alembic ./alembic ; COPY app ./app
USER 10001 (без root)
ENV API_HOST=0.0.0.0 API_IN_CONTAINER=1 PATH=/app/.venv/bin:$PATH
CMD ["sh", "-c", "alembic upgrade head && exec python -m app.api"]
HEALTHCHECK через python -c urllib на http://127.0.0.1:8000/health
```

Шар залежностей кешується окремо від коду. `exec` робить API PID 1, тож `docker compose down`
надсилає SIGTERM прямо в uvicorn і `lifespan` коректно зупиняє планувальник. Якщо міграції
впали, `&&` не дає стартувати API, а помилка лишається в логах (вимога «Автоматичні міграції»).

### 3. Образ фронтенду і nginx

```
FROM node:24-alpine AS build   → npm ci && npm run build
FROM nginx:alpine              → COPY dist /usr/share/nginx/html; COPY nginx.conf
```

`nginx.conf`: `location /api/ { proxy_pass http://backend:8000/; }` — завершальний `/` відрізає
префікс так само, як Vite. `proxy_read_timeout 60s`, бо тест Telegram може тривати до ~35 с.
Решта — статика з `index.html` за замовчуванням.

### 4. docker-compose

```
postgres: без змін (порт 127.0.0.1:5432)
backend:  build ./backend; env_file .env (TELEGRAM_BOT_TOKEN та ін.);
          environment DATABASE_URL=postgresql+asyncpg://dam:dam@postgres:5432/dam (перекриває .env);
          depends_on postgres: service_healthy; ports 127.0.0.1:8000:8000
backend:  healthcheck → /health
web:      build ./frontend; depends_on backend: service_healthy; ports 127.0.0.1:8080:80
```

`env_file` для backend позначено `required: false`, але Makefile однаково створює `.env`
заздалегідь. `DATABASE_URL` у `environment` перекриває localhost-адресу з `.env`, тож той самий `.env`
підходить і для хоста, і для контейнера.

### 5. Makefile

```
help (типова)  — перелік цілей з описом (з коментарів ## у Makefile)
up             — .env з .env.example за потреби; docker compose up -d --build --wait; URL
down           — docker compose down (томи лишаються)
logs, ps       — docker compose logs -f / ps
backfill       — docker compose exec backend python -m app.backfill; якщо backend не запущено —
                 підказка `make up`
clean          — підтвердження (read) або FORCE=1; docker compose down -v --rmi local
```

`--wait` чекає на healthcheck усіх сервісів; якщо не дочекався — ненульовий код, і Makefile
друкує підказку `make logs`. `--rmi local` видаляє лише образи, зібрані compose (не `postgres`,
`nginx` тощо з реєстру — їх можуть використовувати інші проєкти).

### 6. README

`README.md` у корені submission: що це, вимоги (Docker, make), `make up` → адреса, `make backfill`,
Telegram-токен у `.env`, `make down` / `make clean`, і посилання на `docs/` для розробки.

## Risks / Trade-offs

- [Порт 5432, 8000 або 8080 уже зайнятий на машині тестувальника] → `make up` впаде з
  повідомленням Docker; README пояснює, як змінити порт. Параметризація портів — поза обсягом.
- [Перший `make up` одразу робить плановий збір з ОРЕЕ] → так і задумано (зріз 8); без історії
  графік покаже лише поточний квартал, README радить `make backfill`.
- [Маркери контейнера можуть бути відсутні в екзотичних рантаймах] → тоді запуск явно впаде з
  поясненням, а не відкриє порт мовчки; безпечна відмова.
- [Бекфіл ~29 файлів з паузою 2 с — кілька хвилин] → `make backfill` показує прогрес у терміналі.
