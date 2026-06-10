"""middlewares/registration.py"""
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message

logger = logging.getLogger(__name__)


class RegistrationMiddleware(BaseMiddleware):
    def __init__(self, db):
        super().__init__()
        self.db = db

    async def __call__(self, handler: Callable[[TelegramObject, dict], Awaitable[Any]], event: TelegramObject, data: dict) -> Any:
        try:
            # In aiogram v3, the user who triggered the event is in data["event_from_user"]
            u = data.get("event_from_user")
            if u and not u.is_bot:
                await self.db.upsert_user(
                    user_id=u.id,
                    username=u.username or "",
                    first_name=u.first_name or "",
                    join_date=datetime.utcnow().isoformat(),
                    last_activity=datetime.utcnow().isoformat(),
                )
        except Exception:
            logger.exception("Registration middleware error")
        return await handler(event, data)