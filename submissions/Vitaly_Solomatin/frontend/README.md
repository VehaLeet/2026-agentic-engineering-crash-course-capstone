# OREE DAM Monitor — frontend

React + TypeScript + Vite + Zustand. Фронтенд звертається до backend через проксі Vite
на тому самому origin: `/api/*` → backend без префікса `/api`. CORS не потрібен.

## Запуск для розробки

Потрібні Node.js ≥ 20, Docker і `uv`. У корені репозиторію має бути `.env` (див. `.env.example`),
зокрема `API_USERNAME` і `API_PASSWORD`.

```sh
# 1. База і backend (з кореня репозиторію)
docker compose up -d postgres
set -a && . ./.env && set +a
cd backend && uv run uvicorn app.api.main:app --workers 1     # http://localhost:8000

# 2. Frontend (в іншому терміналі)
cd frontend
npm ci
npm run dev                                                   # http://localhost:5173
```

Backend на іншій адресі: `VITE_API_TARGET=http://localhost:8001 npm run dev`.
Змінна читається лише конфігурацією dev-сервера і в зібраний бандл не потрапляє.

## Вхід

Окремої форми входу немає. На перший захищений запит backend відповідає 401 з
`WWW-Authenticate: Basic`, і браузер показує системне вікно логіна. Облікові дані — ті самі
`API_USERNAME` / `API_PASSWORD`. Браузер пам'ятає їх до закриття, кнопки «Вийти» немає.

Якщо вікно не з'явилось або ви натиснули «Скасувати», сторінка покаже «Потрібна
автентифікація» з посиланням «Увійти»: воно відкриває захищену адресу напряму, і браузер
гарантовано запитає пароль.

## Перевірки

```sh
npm run typecheck   # tsc
npm run lint        # oxlint
npm test            # vitest (jsdom), без мережі і без backend
npm run build       # статичні файли в dist/
```
