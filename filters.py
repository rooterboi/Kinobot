"""Maxsus filtrlar."""
from __future__ import annotations

from aiogram import Bot, F
from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from utils import is_admin

# Buyruq bo'lmagan matn (state qadamlarida buyruqlar o'tib ketishi uchun)
TEXT = F.text & ~F.text.startswith("/")


class AdminFilter(BaseFilter):
    async def __call__(self, event: TelegramObject, bot: Bot, db, config) -> bool:
        user = getattr(event, "from_user", None)
        if user is None:
            return False
        return await is_admin(db, config, bot.id, user.id)
