# OREE DAM Monitor — запуск усього сервісу в Docker. Потрібні лише Docker і make.
# Усі порти лише на 127.0.0.1: UI http://127.0.0.1:8080, API :8000, Postgres :5432.
# Перевірка коду (make check) запускається локально: крім Docker, потрібні uv і Node зі
# встановленими залежностями фронтенду (cd frontend && npm ci).

COMPOSE := docker compose
UI_URL  := http://127.0.0.1:8080

.DEFAULT_GOAL := help
.PHONY: help up down logs ps backfill clean check check-hooks check-backend check-frontend

help: ## Показати доступні команди
	@echo "OREE DAM Monitor — команди:"
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-15s %s\n", $$1, $$2}'

.env:
	@cp .env.example .env
	@echo "Створено .env з .env.example. Токен Telegram (необов'язково): TELEGRAM_BOT_TOKEN у .env."

up: .env ## Зібрати й запустити сервіс, дочекатися готовності
	@$(COMPOSE) up -d --build --wait || { echo "Сервіс не піднявся. Подивіться журнали: make logs"; exit 1; }
	@echo "Готово: $(UI_URL)"
	@echo "Історія РДН з 2019 року: make backfill"

down: .env ## Зупинити сервіс (дані бази зберігаються)
	@$(COMPOSE) down

logs: .env ## Журнали всіх сервісів у реальному часі
	@$(COMPOSE) logs -f

ps: .env ## Стан сервісів
	@$(COMPOSE) ps

backfill: .env ## Завантажити історію РДН з 01.07.2019 (кілька хвилин)
	@$(COMPOSE) ps --status running --services | grep -qx backend || { echo "Сервіс не запущено: спершу make up"; exit 1; }
	@$(COMPOSE) exec backend python -m app.backfill

clean: .env ## Прибрати все: контейнери, базу даних і зібрані образи (.env лишається)
	@if [ "$(FORCE)" != "1" ]; then \
		printf "Це безповоротно видалить базу даних і образи сервісу. Продовжити? [y/N] "; \
		read answer; [ "$$answer" = "y" ] || [ "$$answer" = "Y" ] || { echo "Скасовано."; exit 1; }; \
	fi
	@$(COMPOSE) down -v --rmi local
	@echo "Прибрано. .env збережено."

# Єдиний гейт перед «готово»: зупиняється на першій червоній частині.
# Від швидкого до повільного, щоб зламаний хук чи тест було видно за секунди, а не після build.
check: check-hooks check-backend check-frontend ## Усі перевірки: хуки, тести backend і frontend, lint, build
	@echo "check: усе зелене"

check-hooks: ## Самоперевірка хуків .claude/
	@node scripts/hooks-selftest.mjs

check-backend: ## Тести backend (testcontainers-Postgres, потрібен запущений Docker)
	@docker info >/dev/null 2>&1 || { echo "Docker не запущено: тести backend піднімають Postgres у testcontainers"; exit 1; }
	@cd backend && uv run -q pytest -q

check-frontend: ## Тести frontend (і в інших часових поясах), lint, typecheck і build
	@[ -d frontend/node_modules ] || { echo "Немає frontend/node_modules: спершу cd frontend && npm ci"; exit 1; }
	@cd frontend && npm test --silent && npm run --silent test:tz && npm run --silent lint && npm run --silent build
