## Context

- Збір — це `collect_once(...)` (`app/collection/collect.py`). Він уже приймає `trigger`, бере
  неблокувальне advisory lock і пише журнал. `RUN_TRIGGERS` і check-обмеження БД уже містять
  `scheduled`, тож міграція журналу не потрібна.
- API запускається одним воркером (`app/api/__main__.py`). `create_app` у `lifespan` збирає
  залежності й тримає фонові ручні запуски в `RunManager`, який під час зупинки скасовує
  незавершені задачі.
- APScheduler згаданий у брифі, але в `pyproject.toml` його ще немає.
- Тести API (`tests/test_api.py::running`) піднімають справжній `lifespan` на тестовому Postgres
  і рахують рядки журналу. Стартовий плановий запуск зламав би ці підрахунки.

## Goals / Non-Goals

**Goals:**
- Один механізм запуску збору для ручного і планового шляху: відрізняється лише `trigger`.
- Налаштування розкладу лежать у БД, а розклад у пам'яті — лише похідна від них.
- Тести розкладу не чекають реальних хвилин.

**Non-Goals:**
- Кілька процесів або воркерів із планувальником і будь-яка координація між ними, крім уже
  наявного advisory lock.
- Загальне сховище налаштувань «ключ → значення». Зріз 9 додасть свої колонки в ту саму таблицю.

## Decisions

### 1. APScheduler 3.x, `AsyncIOScheduler`, пам'ятний jobstore

`apscheduler>=3.10,<4`. Гілка 3.x стабільна і підтримує coroutine-jobs в `AsyncIOScheduler` на
тому самому event loop, що й FastAPI. У 4.x інший API, і гілка довго лишалась pre-release.
Jobstore лишається в пам'яті: під час кожного старту job будується заново з `app_settings`.
Персистентний jobstore (SQLAlchemyJobStore) зробив би стан APScheduler другим джерелом правди
поряд із таблицею налаштувань, а ще потребував би синхронного драйвера.

*Альтернативи:* власний цикл `asyncio.sleep`. Він простіший, але бриф прямо називає APScheduler, а
`max_instances`, `coalesce` і `reschedule_job` довелося б писати й тестувати самим. Окремий
процес планувальника зараз не потрібен: воркер один, а advisory lock і так захищає від
перетину з CLI чи бекфілом.

### 2. Параметри job

```
add_job(tick, IntervalTrigger(minutes=N), id="collect",
        next_run_time=<now>,     # стартовий запуск одразу
        max_instances=1,         # тік пропускається, поки попередній плановий триває
        coalesce=True,           # кілька прострочених тіків зливаються в один
        misfire_grace_time=60)   # затримка event loop до хвилини не губить тік
```

`max_instances=1` дає «тік пропускається без запису в журнал»: APScheduler лише пише
попередження в лог. Перетин із ручним збором або бекфілом вирішує advisory lock, і такий
запуск отримує `skipped_locked` у журналі. Тіки, пропущені, поки процес не працював,
наздогнати фізично неможливо: jobstore у пам'яті, і після старту буде рівно один стартовий запуск.

### 3. Тік іде через `RunManager`

```
async def tick():
    try:
        run_id = await runs.start("scheduled")
        await manager.start(run_id, "scheduled")   # чекаємо задачу — так працює max_instances
    except Exception:
        log.exception("плановий збір не вдалося запустити")
```

`RunManager.start(run_id, trigger)` отримує параметр `trigger`, а job у `lifespan` стає
`job(run_id, trigger)` і викликає `collect_once(..., trigger, run_id, notifier=...)` з опорною
датою `kyiv_today(now())`. Так плановий запуск:
- має ту саму гілку сповіщень, що й ручний;
- скасовується під час зупинки тим самим `manager.shutdown()` і лишає рядок із порожнім
  `finished_at`.

Помилки всередині збору `collect_once` уже перетворює на `error`. Обгортка `try/except`
потрібна лише для збоїв до або навколо нього, наприклад коли БД недоступна на `runs.start`,
щоб виняток не «з'їв» тік мовчки і не зачепив планувальник.

### 4. `CollectScheduler`: тонка обгортка

Модуль `app/scheduling.py`:

```
class CollectScheduler:
    def __init__(self, tick): ...
    def start(self, settings: ScheduleSettings) -> None      # enabled → add_job(next_run_time=now)
    def apply(self, settings: ScheduleSettings) -> None      # enabled → reschedule_job(IntervalTrigger(N))
                                                             #   (або add_job без next_run_time, якщо job немає)
                                                             # disabled → remove_job, якщо є
    def next_run_at(self) -> datetime | None
    async def shutdown(self) -> None                         # scheduler.shutdown(wait=False)
```

`reschedule_job` із новим `IntervalTrigger` дає `next_run_at = now + N`, і це збігається зі
специфікацією і для зміни інтервалу, і для повторного ввімкнення. `resume_job` відкинуто: він
рахує наступний тік від старого `start_date` тригера, а не від моменту зміни. Вимкнення робиться
через `remove_job`: job, що вже виконується, APScheduler не перериває.

### 5. Схема БД: однорядкова `app_settings`

Міграція `0004_app_settings`:

```
app_settings
  id                        SMALLINT PRIMARY KEY  CHECK (id = 1)
  schedule_enabled          BOOLEAN   NOT NULL DEFAULT true
  collect_interval_minutes  INTEGER   NOT NULL DEFAULT 60
                            CHECK (collect_interval_minutes BETWEEN 5 AND 1440)
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
-- upgrade: INSERT INTO app_settings (id) VALUES (1)
```

Одна типізована таблиця з одним рядком замість «ключ → значення»: типи й межі перевіряє БД, а
зріз 9 просто додасть колонку `notifications_enabled`. Межі 5…1440 записано константами в
`app/storage/models.py` і використано і в check-обмеженні, і у валідації API.

`ScheduleSettingsStore` (`app/settings.py`): `get()` робить
`INSERT ... ON CONFLICT DO NOTHING` рядка з типовими значеннями й читає його (самолікування,
якщо рядок видалили руками), а `update(enabled, interval)` оновлює рядок і `updated_at`.
Модель і таблицю треба додати до `TRUNCATE` у `tests/conftest.py`. Після `TRUNCATE` `get()`
знову поверне типові значення.

### 6. Контракт API

```
GET /settings/schedule
  200 {"enabled": true, "interval_minutes": 60, "next_run_at": "2026-09-29T11:00:00Z" | null}

PUT /settings/schedule
  body {"enabled": <bool>, "interval_minutes": <int 5..1440>}   -- обидва поля обов'язкові
  200 — те саме тіло, що й GET, уже після перепланування
  422 — відсутнє поле, не той тип (strict: "15", 7.5, true не приймаються як ціле), поза межами
```

Pydantic-модель зі `StrictBool` і `Field(strict=True, ge=5, le=1440)`. Порядок обробки такий:
валідація, потім запис у БД (коміт), потім `scheduler.apply`, потім відповідь. Якщо запис у БД
зірвався, розклад не чіпається (500). Два `PUT` одночасно серіалізуються через `asyncio.Lock`,
щоб порядок застосування до планувальника збігався з порядком комітів. `PUT`, а не `PATCH`:
ресурс маленький і завжди надсилається цілим, а UI зрізу 11b показуватиме обидва поля в одній
формі.

`next_run_at` серіалізується як час із часовим поясом, як і `started_at` у `/runs`.

### 7. `create_app(..., scheduler: bool = True)`

Прапорець лише для тестів. `running()` у `tests/test_api.py` передає `False`, тож наявні
підрахунки рядків не змінюються, а тести розкладу вмикають його явно. Коли `scheduler=False`,
маршрути `/settings/schedule` працюють, а `next_run_at` завжди `null`. Налаштування все одно
зберігаються, щоб тести API могли перевірити контракт і валідацію без планувальника.

## Risks / Trade-offs

- [Кожен рестарт API (наприклад, `--reload` під час розробки) запускає збір] → він дешевий
  (1–2 файли по ~110 КБ), ідемпотентний, а незмінний файл дає ранній вихід за хешем.
- [Хтось запустить uvicorn із кількома воркерами → кілька планувальників] → запускач уже фіксує
  `workers=1`; навіть тоді advisory lock не дасть писати одночасно, лише додасть рядки
  `skipped_locked`. У модулі це задокументовано.
- [Пропуск тіку через `max_instances` видно лише в логах, не в журналі] → свідомо: журнал
  описує запуски, а не наміри. Збір, довший за 5 хвилин, сам по собі є аномалією, і рядок
  попереднього запуску в журналі видно.
- [БД закомітила новий інтервал, а `apply` упав] → БД лишається джерелом правди, наступний
  рестарт вирівняє розклад; помилку буде залоговано й повернуто як 500.
- [Тести з планувальником залежать від реального часу] → стартовий запуск перевіряється
  очікуванням рядка журналу з таймаутом, неперекривання — примусовим `next_run_time=now` на job
  під час загейтованого джерела, а інтервали — через значення `next_run_at`, без очікування
  хвилин.

## Migration Plan

1. `uv add "apscheduler>=3.10,<4"`.
2. `alembic upgrade head` створює `app_settings` з рядком за замовчуванням. Відкат:
   `alembic downgrade 0003_telegram` видаляє таблицю, дані журналу не зачіпаються.
3. Після рестарту API розклад запускається сам з інтервалом 60 хвилин. Щоб старт відбувся без
   автоматичного збору, розклад вимикають через `PUT /settings/schedule` до рестарту.
