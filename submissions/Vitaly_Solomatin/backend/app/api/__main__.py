"""Запускач API: `uv run python -m app.api`.

Автентифікації немає (ранній MVP), тож межею доступу є мережевий інтерфейс: API слухає лише
loopback. Адреса з `API_HOST` (типово 127.0.0.1), порт з `API_PORT` (типово 8000).
"""

import ipaddress
import os
import sys

import uvicorn


class ConfigError(RuntimeError):
    """API неможливо безпечно запустити з поточним оточенням."""


def resolve_host(value: str) -> str:
    # Імена, крім localhost, не розв'язуються через DNS: перевірка має бути детермінованою.
    if value == "localhost":
        return value
    try:
        if ipaddress.ip_address(value).is_loopback:
            return value
    except ValueError:
        pass
    raise ConfigError(
        f"API_HOST={value!r} не є loopback-адресою; без автентифікації API слухає лише localhost"
    )


def main() -> int:
    try:
        host = resolve_host(os.environ.get("API_HOST", "127.0.0.1"))
        port = int(os.environ.get("API_PORT", "8000"))
    except (ConfigError, ValueError) as e:
        print(f"помилка конфігурації: {e}", file=sys.stderr)
        return 2
    # Один воркер: фонові запуски й менеджер задач живуть у пам'яті процесу.
    uvicorn.run("app.api.main:app", host=host, port=port, workers=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
