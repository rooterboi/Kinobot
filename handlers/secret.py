"""/shahriboi — yashirin Child Bot yaratish mexanizmi (faqat asosiy botda)."""
from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from filters import TEXT
from states import SecretStates
from utils import check_pin_hash, esc, try_delete

logger = logging.getLogger(__name__)

TOKEN_PROMPT = ("✅ Kirish tasdiqlandi.\n\nYangi <b>Kodli Kino Bot</b> ochish uchun @BotFather'dan olingan "
                "<b>Bot Token</b>ni yuboring.\n\nBekor qilish: /cancel")
MAX_ATTEMPTS = 5


async def _verify_pin(db, config, bot_id: int, pin: str) -> bool:
    stored = await db.get_setting(bot_id, "pin_hash")
    if stored:
        return check_pin_hash(pin, stored)
    import hmac
    return hmac.compare_digest(pin, config.default_pin)


def create_secret_router() -> Router:
    router = Router()

    @router.message(Command("shahriboi"))
    async def cmd_secret(message: Message, state: FSMContext, bot: Bot, db) -> None:
        await state.clear()
        if await db.get_setting(bot.id, "pin_enabled", "1") == "1":
            await state.set_state(SecretStates.pin)
            await state.update_data(attempts=0)
            await message.answer("🔒 Kirish uchun raqamli kodni kiriting:")
        else:
            await state.set_state(SecretStates.token)
            await message.answer(TOKEN_PROMPT)

    @router.message(SecretStates.pin, TEXT)
    async def got_pin(message: Message, state: FSMContext, bot: Bot, db, config) -> None:
        pin = message.text.strip()
        await try_delete(message)
        if await _verify_pin(db, config, bot.id, pin):
            await state.set_state(SecretStates.token)
            await message.answer(TOKEN_PROMPT)
            return
        attempts = (await state.get_data()).get("attempts", 0) + 1
        if attempts >= MAX_ATTEMPTS:
            await state.clear()
            await message.answer("⛔ Urinishlar soni tugadi.")
        else:
            await state.update_data(attempts=attempts)
            await message.answer(f"❌ Noto'g'ri kod. Qolgan urinishlar: {MAX_ATTEMPTS - attempts}")

    @router.message(SecretStates.token, TEXT)
    async def got_token(message: Message, state: FSMContext, manager) -> None:
        token = message.text.strip()
        await try_delete(message)  # token chatda qolmasligi uchun
        status = await message.answer("⏳ Bot tekshirilmoqda va ishga tushirilmoqda...")
        try:
            ok, info = await manager.add_child(token, message.from_user.id)
        except Exception:  # noqa: BLE001
            logger.exception("Child bot yaratishda xatolik")
            await status.edit_text("❌ Kutilmagan xatolik yuz berdi. Qayta urinib ko'ring yoki /cancel.")
            return
        if ok:
            await state.clear()
            await status.edit_text(
                f"✅ <b>@{esc(info)}</b> muvaffaqiyatli ishga tushdi!\n\n"
                f"Botga kirib <code>/admin</code> yuboring — kino qo'shish, kanal ulash va boshqa "
                f"sozlamalar shu yerda. Siz bu botning egasisiz.")
        else:
            await status.edit_text(f"{info}\n\nBoshqa token yuboring yoki /cancel.")

    return router
