import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Застосунок неможливо безпечно запустити з поточним оточенням."""


@dataclass(frozen=True, slots=True)
class ApiSettings:
    username: str
    password: str

    def __repr__(self) -> str:  # пароль не потрапляє в логи й трейсбеки
        return f"ApiSettings(username={self.username!r}, password='***')"

    @classmethod
    def from_env(cls) -> "ApiSettings":
        username = os.environ.get("API_USERNAME", "")
        password = os.environ.get("API_PASSWORD", "")
        missing = [name for name, value in (("API_USERNAME", username), ("API_PASSWORD", password)) if not value]
        if missing:
            # Закрито за замовчуванням: API без пароля гірший, ніж API, що не стартував.
            raise ConfigError(f"не задано в оточенні: {', '.join(missing)}")
        return cls(username, password)
