"""Запускач API: `uv run python -m app.api`.

Автентифікації немає (ранній MVP), тож межею доступу є мережевий інтерфейс: API слухає лише
loopback. Адреса з `API_HOST` (типово 127.0.0.1), порт з `API_PORT` (типово 8000).

Виняток — явний режим контейнера (`API_IN_CONTAINER=1`): усередині контейнера дозволено `0.0.0.0`,
бо інакше до API не дістануться ні nginx, ні хост. Межу тоді тримає docker-compose, що публікує
порти лише на 127.0.0.1. Поза контейнером цей режим відмовляє, щоб випадково скопійована змінна
не відкрила API в мережу.
"""

import ipaddress
import os
import sys
from collections.abc import Iterable
from pathlib import Path

import uvicorn


class ConfigError(RuntimeError):
    """API неможливо безпечно запустити з поточним оточенням."""


# Маркери, які рантайм створює всередині контейнера: Docker і Podman.
CONTAINER_MARKERS = (Path("/.dockerenv"), Path("/run/.containerenv"))
ANY_ADDRESS = "0.0.0.0"


def in_container(markers: Iterable[Path] | None = None) -> bool:
    return any(m.exists() for m in (CONTAINER_MARKERS if markers is None else markers))


def resolve_host(value: str, container_mode: bool = False, markers: Iterable[Path] | None = None) -> str:
    if container_mode and not in_container(markers):
        raise ConfigError(
            "API_IN_CONTAINER=1 діє лише всередині контейнера; поза ним API слухає лише localhost"
        )
    # Імена, крім localhost, не розв'язуються через DNS: перевірка має бути детермінованою.
    if value == "localhost":
        return value
    if container_mode and value == ANY_ADDRESS:
        return value  # межу тримає публікація портів лише на 127.0.0.1 у docker-compose
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
        container_mode = os.environ.get("API_IN_CONTAINER") == "1"
        host = resolve_host(os.environ.get("API_HOST", "127.0.0.1"), container_mode)
        port = int(os.environ.get("API_PORT", "8000"))
    except (ConfigError, ValueError) as e:
        print(f"помилка конфігурації: {e}", file=sys.stderr)
        return 2
    # Один воркер: фонові запуски й менеджер задач живуть у пам'яті процесу.
    uvicorn.run("app.api.main:app", host=host, port=port, workers=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
