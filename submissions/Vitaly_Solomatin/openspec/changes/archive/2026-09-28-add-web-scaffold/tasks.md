## 1. Каркас проєкту

- [x] 1.1 Згенерувати `frontend/` з `npm create vite@latest frontend -- --template react-ts` і
      прибрати демо-вміст шаблону (логотипи, лічильник, демо-CSS); перевірка: `npm run build`
      у `frontend/` завершується успішно, і в `src/` немає файлів шаблону, крім `main.tsx`.
- [x] 1.2 Додати `zustand`; для розробки — `vitest`, `@testing-library/react`,
      `@testing-library/jest-dom`, `jsdom`; перевірка: `npm ci` на чистому клоні встановлює все
      без помилок, `package-lock.json` закомічено.
- [x] 1.3 Додати до репозиторію `.gitignore` для `frontend/node_modules/` і `frontend/dist/`;
      перевірка: після `npm ci && npm run build` `git status` не показує ні `node_modules`, ні `dist`.
- [x] 1.4 Налаштувати Vitest (jsdom) і скрипти `test`, `typecheck` (`tsc --noEmit`), `lint`;
      перевірка: `npm test`, `npm run typecheck` і `npm run lint` проходять на порожньому наборі
      тестів.

## 2. Проксі до API

- [x] 2.1 Налаштувати у `vite.config.ts` проксі `/api/*` → `VITE_API_TARGET` (типово
      `http://localhost:8000`) із зняттям префікса `/api`; перевірка: при запущеному backend
      `curl localhost:5173/api/health` повертає `{"status":"ok"}`.
- [x] 2.2 Інша адреса backend через змінну оточення; перевірка: backend на порту 8001 і
      `VITE_API_TARGET=http://localhost:8001 npm run dev` — `curl localhost:5173/api/health`
      повертає `{"status":"ok"}`.
- [x] 2.3 Проксі передає 401 і `WWW-Authenticate` без змін; перевірка: `curl -i
      localhost:5173/api/status` показує 401 і заголовок `WWW-Authenticate: Basic`.

## 3. Клієнт API, сховище, панель

- [x] 3.1 Типи `Run` і `SystemStatus` за контрактом `http-api`; перевірка: `npm run typecheck`
      проходить, і тест клієнта використовує реальний приклад відповіді `/status` з
      `design.md` зрізу 5.
- [x] 3.2 `getHealth` і `getStatus` з розрізненими помилками; перевірка: тести з підміненим
      `fetch` стверджують `ApiUnauthorized` на 401, `ApiUnavailable` на 502, 504 і мережеву помилку,
      `ApiContractError` на 200 без `recent_errors`, і що `Authorization` вручну не додається.
- [x] 3.3 `formatKyiv(iso)`; перевірка: тест стверджує, що `2026-09-28T09:00:00Z` дає рядок з
      `12:00` і `28.09`, а `2026-12-28T09:00:00Z` (зимовий час) — з `11:00`.
- [x] 3.4 Сховище `useConnection` з `check()`; перевірка: тести стверджують стан `unavailable`,
      коли `/health` недоступний, і що `/status` тоді не викликається; `unauthorized` на 401 від
      `/status`; `error` на `ApiContractError`; `ok` з часами на успіх.
- [x] 3.5 `ConnectionPanel` з чотирма станами і посиланням «Увійти» на `/api/status` у стані
      `unauthorized`; перевірка: тести рендерингу для кожного стану, включно з «ще не було» для
      порожнього журналу і наявністю посилання «Увійти».
- [x] 3.6 `App` викликає `check()` при монтуванні; перевірка: тест стверджує один виклик
      `check()` при першому рендері.

## 4. Живий запуск і документація

- [x] 4.1 Запустити backend і `npm run dev`, відкрити `http://localhost:5173` у реальному
      браузері; перевірка: з'являється системне вікно логіна, після введення кредів панель
      показує «з'єднання в порядку» і часи за Києвом. Результат (браузер, чи вікно з'явилось на
      `fetch`, чи знадобилось «Увійти») зафіксовано у звіті.
- [x] 4.2 У тому самому браузері натиснути «Скасувати» у вікні логіна (новий приватний сеанс);
      перевірка: панель показує «потрібна автентифікація» з посиланням «Увійти», і перехід за ним
      відкриває вікно логіна.
- [x] 4.3 Зупинити backend при відкритій сторінці й оновити її; перевірка: панель показує
      «backend недоступний», а не «потрібна автентифікація».
- [x] 4.4 Написати `frontend/README.md`: як запустити backend і frontend разом, змінна
      `VITE_API_TARGET`, як проходить вхід; перевірка: команди з README виконано на чистому клоні,
      і застосунок відкривається.
- [x] 4.5 Оновити `docs/roadmap.md`: статус зрізу 10a; перевірка: рядок `add-web-scaffold` має
      статус «виконано».
- [x] 4.6 Прогнати `npm run typecheck && npm run lint && npm test && npm run build`, backend
      `pytest` і `openspec validate add-web-scaffold --strict`; перевірка: усе успішно, і кожен
      сценарій зі `specs/web-app/spec.md` має відповідний тест або ручну перевірку групи 4.
