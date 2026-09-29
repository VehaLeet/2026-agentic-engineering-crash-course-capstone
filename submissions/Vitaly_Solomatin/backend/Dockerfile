# Образ API з планувальником. Запуск — через docker-compose (див. Makefile у корені).
FROM ghcr.io/astral-sh/uv:0.9 AS uv

FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

# Залежності окремим шаром: зміна коду не перевстановлює їх.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

RUN useradd --system --uid 10001 app
USER app

# Режим контейнера: 0.0.0.0 лише всередині контейнера; назовні compose публікує порт на 127.0.0.1.
ENV PATH=/app/.venv/bin:$PATH API_HOST=0.0.0.0 API_PORT=8000 API_IN_CONTAINER=1 PYTHONUNBUFFERED=1
EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=12 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

# Міграції перед стартом; якщо вони впали, API не стартує. exec — API стає PID 1 і отримує SIGTERM.
CMD ["sh", "-c", "alembic upgrade head && exec python -m app.api"]
