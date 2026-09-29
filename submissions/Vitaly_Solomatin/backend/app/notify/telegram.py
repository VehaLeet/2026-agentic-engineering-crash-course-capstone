"""Прямі виклики Bot API (sendMessage, getUpdates) через httpx (бриф: без фреймворку ботів)."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx

API_BASE = "https://api.telegram.org"


class TelegramError(Exception):
    """Доставку не вдалося виконати. Текст уже очищено від токена."""


class TelegramClient:
    def __init__(
        self,
        token: str,
        base_url: str = API_BASE,
        timeout: float = 10.0,
        attempts: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.attempts = attempts
        self.transport = transport
        self.sleep = sleep

    def redact(self, text: str) -> str:
        """URL Bot API містить токен, а httpx вставляє URL у тексти винятків — токен не має втекти."""
        return text.replace(self._token, "***") if self._token else text

    async def send(self, chat_id: str, text: str) -> int:
        """Надіслати повідомлення; повертає кількість спроб. Кидає TelegramError."""
        _, attempts = await self._call(
            "sendMessage", {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        )
        return attempts

    async def get_updates(self) -> list[dict]:
        """Оновлення, які Telegram ще зберігає (до 24 год). Без offset: нічого не підтверджується.

        allowed_updates теж не передаємо: Telegram запам'ятовує його для бота, а читання не має
        змінювати налаштувань. Типовий набір уже містить повідомлення і my_chat_member.
        """
        result, _ = await self._call("getUpdates", {"timeout": 0, "limit": 100})
        return result if isinstance(result, list) else []

    async def _call(self, method: str, body: dict) -> tuple[object, int]:
        """Виклик Bot API з повторами; повертає (result, кількість спроб). Кидає TelegramError."""
        url = f"{self.base_url}/bot{self._token}/{method}"
        last = "невідома помилка"
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            for attempt in range(1, self.attempts + 1):
                try:
                    r = await client.post(url, json=body)
                except httpx.TransportError as e:  # мережа, таймаут
                    last = f"{type(e).__name__}: {e}"
                    if attempt < self.attempts:
                        await self.sleep(2 ** (attempt - 1))
                    continue
                payload = _json(r)
                if r.status_code == 200:
                    return payload.get("result"), attempt
                description = payload.get("description") or f"HTTP {r.status_code}"
                last = f"HTTP {r.status_code}: {description}"
                if r.status_code == 429 or r.status_code >= 500:
                    if attempt < self.attempts:
                        retry_after = (payload.get("parameters") or {}).get("retry_after")
                        await self.sleep(float(retry_after) if retry_after else 2 ** (attempt - 1))
                    continue
                raise TelegramError(self.redact(last))  # 400/403/409: повтор не допоможе
        raise TelegramError(self.redact(f"{self.attempts} спроби невдалі: {last}"))


def _json(response: httpx.Response) -> dict:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}
