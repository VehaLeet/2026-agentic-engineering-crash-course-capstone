# OREE DAM Monitor — frontend

React + TypeScript + Vite + Zustand. Фронтенд звертається до backend через проксі Vite
на тому самому origin: `/api/*` → backend без префікса `/api`. CORS не потрібен.

## Запуск для розробки

Потрібні Node.js ≥ 20, Docker і `uv`. У корені репозиторію має бути `.env` (див. `.env.example`).

```sh
# 1. База і backend (з кореня репозиторію)
docker compose up -d postgres
set -a && . ./.env && set +a
cd backend && uv run python -m app.api                       # http://localhost:8000

# 2. Frontend (в іншому терміналі)
cd frontend
npm ci
npm run dev                                                   # http://localhost:5173
```

Backend на іншій адресі: `VITE_API_TARGET=http://localhost:8001 npm run dev`.
Змінна читається лише конфігурацією dev-сервера і в зібраний бандл не потрапляє.

## Доступ

Входу немає: це ранній MVP, і API не має автентифікації. Замість неї API слухає лише loopback:
запускач `python -m app.api` відмовиться стартувати, якщо `API_HOST` не `127.0.0.1`, `::1` чи
`localhost`. Не запускайте `uvicorn` напряму з `--host 0.0.0.0`: так API відкриється в мережу без
жодного захисту.

## Перевірки

```sh
npm run typecheck   # tsc
npm run lint        # oxlint
npm test            # vitest (jsdom), без мережі і без backend
npm run build       # статичні файли в dist/
```
