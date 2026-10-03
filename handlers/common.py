"""/start, /cancel va majburiy obuna tekshiruvi."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards import subscribe_kb, user_menu_kb
from utils import esc, is_admin, missing_channels, try_delete

logger = logging.getLogger(__name__)

SUB_TEXT = "📢 Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling, so'ng «✅ Tekshirish» tugmasini bosing:"


async def subscription_markup(bot: Bot, db, config, user_id: int):
    """Obuna talab qilinsa klaviatura, aks holda None qaytaradi (adminlar tekshirilmaydi)."""
    if await is_admin(db, config, user_id=user_id, bot_id=bot.id):
        return None
    missing = await missing_channels(bot, db, user_id)
    return subscribe_kb(missing) if missing else None


def welcome_text(name: str, admin: bool) -> str:
    text = (f"🎬 Salom, <b>{esc(name)}</b>!\n\n"
            "Kino ko'rish uchun <b>raqamli kodni</b> yuboring (masalan: <code>125</code>).\n"
            "Nom yoki janr bo'yicha qidirish uchun uni yozing.")
    if admin:
        text += "\n\n🛠 Admin panel: /admin"
    return text


def create_common_router() -> Router:
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext, bot: Bot, db, config) -> None:
        await state.clear()
        markup = await subscription_markup(bot, db, config, message.from_user.id)
        if markup:
            await message.answer(SUB_TEXT, reply_markup=markup)
            return
        admin = await is_admin(db, config, bot.id, message.from_user.id)
        await message.answer(welcome_text(message.from_user.full_name, admin), reply_markup=user_menu_kb())

    @router.message(Command("cancel"))
    async def cmd_cancel(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("✅ Bekor qilindi.", reply_markup=user_menu_kb())

    @router.callback_query(F.data == "check_sub")
    async def cb_check(cb: CallbackQuery, bot: Bot, db, config) -> None:
        markup = await subscription_markup(bot, db, config, cb.from_user.id)
        if markup:
            await cb.answer("❌ Hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)
            return
        await cb.answer("✅ Rahmat!")
        if cb.message:
            await try_delete(cb.message)
            await cb.message.answer("✅ Obuna tasdiqlandi. Kino kodini yuboring 🍿", reply_markup=user_menu_kb())

    return router
