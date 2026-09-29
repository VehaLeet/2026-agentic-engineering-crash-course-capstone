## 1. Режим контейнера в запускачі API

- [x] 1.1 `resolve_host` з режимом контейнера і перевіркою маркерів `/.dockerenv` /
      `/run/.containerenv`; перевірка: тести `test_launcher.py` стверджують, що в режимі контейнера
      (маркер існує) `0.0.0.0` приймається, `192.168.1.10` відхиляється, а без маркера
      `API_IN_CONTAINER=1` дає помилку конфігурації з поясненням; наявні тести запускача зелені.
- [x] 1.2 `.env.example`: закоментований опис `API_IN_CONTAINER` (лише для Docker); перевірка:
      `test_env_example_has_no_credentials_and_documents_host` зелений.

## 2. Образи

- [x] 2.1 `backend/Dockerfile` і `backend/.dockerignore` (без `.venv`, тестів, кешів); перевірка:
      `docker build backend` проходить, образ працює не від root, `docker run` без маркера-хоста
      стартує з `API_IN_CONTAINER=1`.
- [x] 2.2 `frontend/Dockerfile`, `frontend/nginx.conf` і `frontend/.dockerignore` (без
      `node_modules`, `dist`); перевірка: `docker build frontend` проходить.

## 3. docker-compose

- [x] 3.1 Сервіси `backend` і `web` з healthcheck, залежностями й портами лише на `127.0.0.1`;
      перевірка: тест стверджує, що кожен опублікований порт у `docker compose config --format json`
      має `host_ip: 127.0.0.1`; `test_image_tag_shared_by_compose_and_fixture` зелений.

## 4. Makefile і README

- [x] 4.1 `Makefile` з цілями `help`, `up`, `down`, `logs`, `ps`, `backfill`, `clean`; перевірка:
      `make` показує довідку; `make clean` без підтвердження нічого не видаляє; `make backfill` без
      запущеного стеку підказує `make up`.
- [x] 4.2 `README.md` зі швидким стартом; перевірка: усі команди з README існують у Makefile.
- [x] 4.3 `docs/roadmap.md`: борг «Контейнеризація backend» прибрано, зріз 12 `add-docker-stack`
      позначено «виконано»; перевірка: у «Боргах» немає пункту про контейнеризацію.

## 5. Приймання

- [x] 5.1 Наскрізна перевірка на чистому томі: `make up` → `http://127.0.0.1:8080` відкриває UI,
      `/api/health` через nginx відповідає 200, у журналі запусків є плановий запуск; `make down` і
      `make up` зберігають налаштування; `make clean FORCE=1` прибирає том і образи, `.env` лишається.
      Dev-БД на тому самому порту зупинити заздалегідь або перевіряти після попередження власника.
- [x] 5.2 Бекенд і фронтенд тести зелені (`uv run pytest`, `npm test`, `npm run lint`);
      `openspec validate add-docker-stack --strict` проходить.
