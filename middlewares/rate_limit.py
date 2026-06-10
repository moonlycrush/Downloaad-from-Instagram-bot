"""middlewares/rate_limit.py"""
import time
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, max_per_second: float = 1.0):
        super().__init__()
        self.max_per_second = max_per_second
        self._last = {}  # user_id -> timestamp

    async def __call__(self, handler: Callable[[TelegramObject, dict], Awaitable[Any]], event: TelegramObject, data: dict) -> Any:
        try:
            user_id = None
            update = data.get("update") or event
            if getattr(update, "message", None) and update.message.from_user:
                user_id = update.message.from_user.id
            elif getattr(update, "callback_query", None) and update.callback_query.from_user:
                user_id = update.callback_query.from_user.id
            if user_id:
                now = time.time()
                last = self._last.get(user_id, 0)
                if now - last < (1.0 / self.max_per_second):
                    # Too fast; ignore the update
                    return
                self._last[user_id] = now
        except Exception:
            logger.exception("RateLimit middleware failure")
        return await handler(event, data)