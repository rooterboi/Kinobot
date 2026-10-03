"""Middleware'lar."""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)


class UserTrackingMiddleware(BaseMiddleware):
    """Har bir bot uchun foydalanuvchilarni ro'yxatga oladi va faolligini yangilaydi."""

    def __init__(self, db) -> None:
        self.db = db

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        bot = data.get("bot")
        if user and bot and not user.is_bot:
            try:
                await self.db.touch_user(bot.id, user.id, user.full_name, user.username)
            except Exception:  # noqa: BLE001
                logger.exception("touch_user xatosi")
        return await handler(event, data)
