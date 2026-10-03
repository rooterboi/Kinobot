"""Multi-bot (Child Bot) boshqaruvchisi."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent
from aiogram.utils.token import TokenValidationError, validate_token

from config import Config
from database import Database
from handlers import build_router
from middlewares import UserTrackingMiddleware
from services.gemini import GeminiService

logger = logging.getLogger(__name__)


class BotManager:
    def __init__(self, db: Database, config: Config, gemini: GeminiService) -> None:
        self.db = db
        self.config = config
        self.gemini = gemini
        self.main_bot_id: Optional[int] = None
        self.tasks: dict[int, asyncio.Task] = {}

    @staticmethod
    def _new_bot(token: str) -> Bot:
        return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    def _make_dispatcher(self, is_main: bool) -> Dispatcher:
        dp = Dispatcher(storage=MemoryStorage(), db=self.db, config=self.config,
                        manager=self, gemini=self.gemini)
        tracker = UserTrackingMiddleware(self.db)
        dp.message.outer_middleware(tracker)
        dp.callback_query.outer_middleware(tracker)
        dp.include_router(build_router(is_main))

        async def on_error(event: ErrorEvent) -> bool:
            logger.error("Handlerda xatolik: %s", event.exception, exc_info=event.exception)
            return True

        dp.errors.register(on_error)
        return dp

    def _launch(self, bot: Bot, is_main: bool) -> asyncio.Task:
        dp = self._make_dispatcher(is_main)
        task = asyncio.create_task(self._run(bot, dp), name=f"bot-{bot.id}")
        self.tasks[bot.id] = task
        return task

    async def _run(self, bot: Bot, dp: Dispatcher) -> None:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Bot ishga tushdi: %s", bot.id)
            await dp.start_polling(bot, handle_signals=False,
                                   allowed_updates=dp.resolve_used_update_types())
        except asyncio.CancelledError:
            raise
        except TelegramUnauthorizedError:
            logger.error("Bot %s tokeni bekor qilingan, o'chirildi.", bot.id)
            await self.db.delete_bot(bot.id)
        except Exception:  # noqa: BLE001
            logger.exception("Bot %s to'xtadi", bot.id)
        finally:
            self.tasks.pop(bot.id, None)
            try:
                await bot.session.close()
            except Exception:  # noqa: BLE001
                pass

    async def start_main(self) -> asyncio.Task:
        bot = self._new_bot(self.config.bot_token)
        me = await bot.get_me()
        self.main_bot_id = me.id
        await self.db.upsert_bot(me.id, "", me.username or "", 0, 1)
        return self._launch(bot, is_main=True)

    async def start_saved_children(self) -> None:
        for row in await self.db.list_child_bots():
            try:
                bot = self._new_bot(row["token"])
                self._launch(bot, is_main=False)
            except TokenValidationError:
                logger.error("Saqlangan token yaroqsiz: bot %s", row["bot_id"])
                await self.db.delete_bot(row["bot_id"])

    async def add_child(self, token: str, owner_id: int) -> tuple[bool, str]:
        """Yangi Kino Botni fonda ishga tushiradi. (ok, xabar/username) qaytaradi."""
        token = token.strip()
        try:
            validate_token(token)
        except TokenValidationError:
            return False, "❌ Token formati noto'g'ri."
        bot = self._new_bot(token)
        try:
            me = await bot.get_me()
        except (TelegramUnauthorizedError, TelegramAPIError):
            await bot.session.close()
            return False, "❌ Token yaroqsiz yoki Telegram bilan bog'lanib bo'lmadi."
        except Exception:  # noqa: BLE001
            logger.exception("add_child xatosi")
            await bot.session.close()
            return False, "❌ Kutilmagan xatolik yuz berdi."
        if me.id == self.main_bot_id or me.id in self.tasks:
            await bot.session.close()
            return False, "⚠️ Bu bot allaqachon ulangan."
        await self.db.upsert_bot(me.id, token, me.username or "", owner_id, 0)
        self._launch(bot, is_main=False)
        return True, me.username or ""

    async def shutdown(self) -> None:
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
