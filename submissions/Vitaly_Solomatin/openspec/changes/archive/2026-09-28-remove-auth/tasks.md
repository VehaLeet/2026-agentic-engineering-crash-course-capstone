## 1. Backend: прибрати автентифікацію

- [x] 1.1 Видалити `app/api/settings.py` і `_require_auth`, роутер `api` без залежностей,
      `create_app` без параметра `settings`, прибрати `app.state.protected_router`; перевірка:
      `grep -rn -e "ApiSettings" -e "HTTPBasic" -e "API_PASSWORD" -e "_require_auth" backend/app`
      нічого не знаходить.
- [x] 1.2 Прибрати `AUTH`, `auth=AUTH` і тести відхилення кредів із `tests/test_api.py` і
      `tests/test_prices.py`; перевірка: `grep -rn -e "AUTH" -e "401" backend/tests` не
      знаходить тестів автентифікації, а решта API-тестів зелена.
- [x] 1.3 Тест «жоден маршрут не вимагає облікових даних»: обхід усіх маршрутів застосунку без
      заголовка `Authorization`; перевірка: тест стверджує, що жоден маршрут не повертає 401,
      а `/docs`, `/redoc` і `/openapi.json` — 404.
- [x] 1.4 Тест «застосунок будується без `API_USERNAME` і `API_PASSWORD`»; перевірка: тест
      видаляє обидві змінні з оточення й стверджує, що `create_app()` не кидає виняток.

## 2. Backend: запускач localhost-only

- [x] 2.1 `resolve_host(value)` у `app/api/__main__.py`; перевірка: параметризований тест
      стверджує успіх для `127.0.0.1`, `127.0.0.2`, `::1`, `localhost` і `ConfigError` з адресою в
      повідомленні для `0.0.0.0`, `::`, `192.168.1.10`, `example.com`.
- [x] 2.2 `main()` читає `API_HOST` (типово `127.0.0.1`) і `API_PORT` (типово `8000`) та
      викликає `uvicorn.run(..., workers=1)`; перевірка: тест із підміненим `uvicorn.run`
      стверджує передані `host`, `port`, `workers=1` для типових значень і що на `0.0.0.0`
      `uvicorn.run` не викликається, а код виходу ненульовий.
- [x] 2.3 Живий запуск; перевірка: `uv run python -m app.api` відповідає на
      `curl localhost:8000/status` кодом 200 без кредів, а `API_HOST=0.0.0.0 uv run python -m app.api`
      завершується з помилкою конфігурації, і порт не слухається.

## 3. Frontend: прибрати автентифікацію

- [x] 3.1 Видалити `ApiUnauthorized`; 401 обробляється як `ApiContractError`; перевірка: тест
      клієнта на 401 стверджує `ApiContractError`, і що заголовка `Authorization` немає.
- [x] 3.2 Прибрати стан `unauthorized` з `Connection` і `useConnection`; перевірка:
      `npm run typecheck` проходить, а тести сховища на `ok` / `unavailable` / `error` зелені.
- [x] 3.3 Прибрати стан і посилання «Увійти» з `ConnectionPanel`; перевірка: тест стверджує,
      що жоден стан панелі не містить посилання «Увійти» і тексту «автентифікація».

## 4. Конфігурація і документація

- [x] 4.1 `.env.example`: прибрати `API_USERNAME`, `API_PASSWORD`, додати закоментований
      `API_HOST`; перевірка: тест `.env.example` оновлено відповідно і він зелений.
- [x] 4.2 `docker-compose.yml`: `127.0.0.1:5432:5432`; перевірка: після
      `docker compose up -d postgres` команда `docker compose port postgres 5432` показує
      `127.0.0.1:5432`, а backend-тести й живий API працюють.
- [x] 4.3 `docs/brief.md`: замінити рядки «Доступ до UI» і «TLS» формулюванням із `design.md`;
      перевірка: `grep -n "Basic Auth" docs/brief.md` порожній, а в брифі є «лише localhost».
- [x] 4.4 `docs/roadmap.md`: запис про поворот напряму, переформульований борг TLS, без зрізу
      `add-web-login`; перевірка: розділ боргів не згадує Basic Auth як чинний механізм.
- [x] 4.5 `frontend/README.md`: прибрати розділ «Вхід» і `API_*`, запуск backend через
      `python -m app.api`; перевірка: команди з README виконано, застосунок відкривається без
      жодного вікна входу.
- [x] 4.6 Розділи `Purpose` у `openspec/specs/http-api/spec.md` і `openspec/specs/web-app/spec.md`
      без згадок автентифікації; перевірка: `openspec validate http-api --type spec --strict` і
      те саме для `web-app` проходять.

## 5. Фінальна перевірка

- [x] 5.1 Відкрити `http://localhost:5173` у браузері; перевірка: без жодного вікна входу
      показується «З'єднання з API в порядку» з часами за Києвом.
- [x] 5.2 Прогнати backend `pytest`, frontend `npm run typecheck && npm run lint && npm test &&
      npm run build` і `openspec validate remove-auth --strict`; перевірка: усе успішно, і кожен
      сценарій дельт має тест або ручну перевірку.
