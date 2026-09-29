# OREE DAM Monitor — запуск усього сервісу в Docker. Потрібні лише Docker і make.
# Усі порти лише на 127.0.0.1: UI http://127.0.0.1:8080, API :8000, Postgres :5432.

COMPOSE := docker compose
UI_URL  := http://127.0.0.1:8080

.DEFAULT_GOAL := help
.PHONY: help up down logs ps backfill clean

help: ## Показати доступні команди
	@echo "OREE DAM Monitor — команди:"
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-9s %s\n", $$1, $$2}'

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
