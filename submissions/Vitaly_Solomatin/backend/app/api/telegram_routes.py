"""Налаштування Telegram-сповіщень: вимикач, отримувачі, тестове повідомлення, кандидати.

Токен ніколи не потрапляє у відповіді: назовні видно лише, чи він заданий.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, StrictBool, StrictStr

from app.notify.candidates import candidates_from_updates
from app.notify.message import TEST_TEXT
from app.notify.recipients import InvalidChatId, Recipient, RecipientRepository
from app.notify.telegram import TelegramClient, TelegramError
from app.settings import NotificationSettingsStore

router = APIRouter()

NO_TOKEN = "TELEGRAM_BOT_TOKEN не задано"


class Notifications(BaseModel):
    enabled: bool
    token_configured: bool


class NotificationsUpdate(BaseModel):
    enabled: StrictBool


class RecipientOut(BaseModel):
    chat_id: str
    enabled: bool

    @classmethod
    def of(cls, r: Recipient) -> "RecipientOut":
        return cls(chat_id=r.chat_id, enabled=r.enabled)


class RecipientCreate(BaseModel):
    chat_id: StrictStr


class RecipientUpdate(BaseModel):
    enabled: StrictBool


class TestResult(BaseModel):
    ok: bool
    error: str | None = None


class CandidateOut(BaseModel):
    chat_id: str
    type: str
    title: str
    username: str | None
    last_seen_at: datetime
    added: bool


def _recipients(request: Request) -> RecipientRepository:
    return RecipientRepository(request.app.state.settings.sessions)


def _switch(request: Request) -> NotificationSettingsStore:
    return NotificationSettingsStore(request.app.state.settings.sessions)


def _client(request: Request) -> TelegramClient:
    client = request.app.state.telegram
    if client is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_TOKEN)
    return client


@router.get("/settings/notifications", response_model=Notifications)
async def get_notifications(request: Request) -> Notifications:
    return Notifications(enabled=await _switch(request).enabled(),
                         token_configured=request.app.state.telegram is not None)


@router.put("/settings/notifications", response_model=Notifications)
async def put_notifications(body: NotificationsUpdate, request: Request) -> Notifications:
    enabled = await _switch(request).set_enabled(body.enabled)
    return Notifications(enabled=enabled, token_configured=request.app.state.telegram is not None)


@router.get("/settings/telegram/recipients", response_model=list[RecipientOut])
async def list_recipients(request: Request) -> list[RecipientOut]:
    return [RecipientOut.of(r) for r in await _recipients(request).all()]


@router.post("/settings/telegram/recipients", response_model=RecipientOut, status_code=status.HTTP_201_CREATED)
async def add_recipient(body: RecipientCreate, request: Request, response: Response) -> RecipientOut:
    repo = _recipients(request)
    try:
        added = await repo.add(body.chat_id)
    except InvalidChatId as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))
    if not added:
        response.status_code = status.HTTP_200_OK  # уже є: без дубліката і без зміни enabled
    return RecipientOut.of(await repo.get(body.chat_id))


@router.patch("/settings/telegram/recipients/{chat_id}", response_model=RecipientOut)
async def update_recipient(chat_id: str, body: RecipientUpdate, request: Request) -> RecipientOut:
    recipient = await _recipients(request).set_enabled(chat_id, body.enabled)
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recipient not found")
    return RecipientOut.of(recipient)


@router.delete("/settings/telegram/recipients/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipient(chat_id: str, request: Request) -> Response:
    if not await _recipients(request).remove(chat_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recipient not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/settings/telegram/recipients/{chat_id}/test", response_model=TestResult)
async def test_recipient(chat_id: str, request: Request) -> TestResult:
    # Спершу отримувач: невідомий chat_id ніколи не доходить до Telegram.
    recipient = await _recipients(request).get(chat_id)
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recipient not found")
    client = _client(request)
    try:
        await client.send(recipient.chat_id, TEST_TEXT)  # поза журналом доставок: це діагностика
    except TelegramError as e:  # текст уже без токена
        return TestResult(ok=False, error=str(e))
    return TestResult(ok=True)


@router.get("/settings/telegram/candidates", response_model=list[CandidateOut])
async def list_candidates(request: Request) -> list[CandidateOut]:
    client = _client(request)
    try:
        updates = await client.get_updates()
    except TelegramError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    known = {r.chat_id for r in await _recipients(request).all()}
    return [
        CandidateOut(chat_id=c.chat_id, type=c.type, title=c.title, username=c.username,
                     last_seen_at=c.last_seen_at,
                     added=c.chat_id in known or (c.username is not None and f"@{c.username}" in known))
        for c in candidates_from_updates(updates)
    ]
