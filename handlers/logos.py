"""/logos — Gemini orqali logotip yasash va savol-javob."""
from __future__ import annotations

import logging
import random

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from filters import TEXT
from keyboards import (BTN_LOGO, logo_nav_kb, logo_result_kb, logos_menu_kb, retry_logo_kb)
from services.gemini import GeminiError, GeminiService
from states import LogoStates
from utils import esc, extract_svg, is_admin, reply_long, safe_edit, svg_to_png

logger = logging.getLogger(__name__)

LOGO_SYSTEM = (
    "You are an expert vector logo designer. Respond with ONLY one valid, self-contained SVG document "
    "(single <svg> element, xmlns, viewBox=\"0 0 512 512\"). No markdown, no code fences, no explanations. "
    "Use only basic shapes, paths, gradients and <text> with generic font-family (Arial, sans-serif). "
    "No external images, no scripts, no foreignObject, no external links. Keep it clean, modern, balanced, "
    "with a transparent or simple background and strong contrast. Keep the code under 7000 characters."
)

QA_SYSTEM = (
    "Siz logotip, brending va grafik dizayn bo'yicha tajribali maslahatchisiz. Foydalanuvchi savollariga "
    "o'zbek tilida (u boshqa tilda yozsa, shu tilda) aniq, amaliy va qisqa javob bering: ranglar psixologiyasi, "
    "shriftlar, kompozitsiya, brend nomi, logotip g'oyalari, fayl formatlari (SVG/PNG) va hokazo."
)

MENU_TEXT = "🎨 <b>Logos</b> — AI yordamida logotip yasash va dizayn bo'yicha savol-javob.\n\nTanlang:"


def create_logos_router() -> Router:
    router = Router()

    async def _need_key(target: Message, bot: Bot, db, config, gemini: GeminiService, user_id: int) -> bool:
        """Kalit bo'lmasa False qaytaradi va tushuntirish yuboradi."""
        if await gemini.resolve_key(db, bot.id):
            return True
        hint = "\n\n🛠 Admin: /admin → 🤖 Gemini API orqali kalitni kiriting." \
            if await is_admin(db, config, bot.id, user_id) else ""
        await target.answer("⚠️ AI hozircha faollashtirilmagan: Gemini API kaliti kiritilmagan." + hint)
        return False

    @router.message(Command("logos"))
    @router.message(F.text == BTN_LOGO)
    async def cmd_logos(message: Message, state: FSMContext, bot: Bot, db, config, gemini: GeminiService) -> None:
        await state.clear()
        if not await _need_key(message, bot, db, config, gemini, message.from_user.id):
            return
        await message.answer(MENU_TEXT, reply_markup=logos_menu_kb())

    @router.callback_query(F.data == "logo:menu")
    async def cb_menu(cb: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await cb.answer()
        await safe_edit(cb.message, MENU_TEXT, logos_menu_kb())

    @router.callback_query(F.data == "logo:close")
    async def cb_close(cb: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await cb.answer()
        try:
            await cb.message.delete()
        except (TelegramAPIError, AttributeError):
            pass

    # ---------------- Logotip yasash ----------------
    @router.callback_query(F.data == "logo:make")
    async def cb_make(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(LogoStates.brand)
        await cb.message.answer("✍️ Brend / kompaniya <b>nomini</b> yuboring:\n\n(Bekor qilish: /cancel)")

    @router.message(LogoStates.brand, TEXT)
    async def got_brand(message: Message, state: FSMContext) -> None:
        await state.update_data(brand=message.text.strip()[:60])
        await state.set_state(LogoStates.style)
        await message.answer(
            "🎯 Soha, uslub va ranglarni yozing.\nMasalan: <i>«texnologiya, minimalist, ko'k va oq»</i>\n"
            "Xohlamasangiz «-» yuboring.")

    @router.message(LogoStates.style, TEXT)
    async def got_style(message: Message, state: FSMContext, bot: Bot, db, config, gemini: GeminiService) -> None:
        style = message.text.strip()[:300]
        await state.update_data(style="" if style == "-" else style, svg=None)
        await _generate(message, state, bot, db, gemini)

    @router.callback_query(F.data == "logo:redo")
    async def cb_redo(cb: CallbackQuery, state: FSMContext, bot: Bot, db, gemini: GeminiService) -> None:
        await cb.answer()
        if not (await state.get_data()).get("brand"):
            await cb.message.answer("Avval /logos orqali logotip yarating.")
            return
        await state.update_data(svg=None)
        await _generate(cb.message, state, bot, db, gemini)

    @router.callback_query(F.data == "logo:edit")
    async def cb_edit(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        if not (await state.get_data()).get("svg"):
            await cb.message.answer("Avval /logos orqali logotip yarating.")
            return
        await state.set_state(LogoStates.edit)
        await cb.message.answer("✏️ Nimani o'zgartiramiz? Masalan: <i>«rangni qizilga o'zgartir, shriftni kattaroq qil»</i>")

    @router.message(LogoStates.edit, TEXT)
    async def got_edit(message: Message, state: FSMContext, bot: Bot, db, gemini: GeminiService) -> None:
        await _generate(message, state, bot, db, gemini, instruction=message.text.strip()[:400])

    async def _generate(target: Message, state: FSMContext, bot: Bot, db, gemini: GeminiService,
                        instruction: str | None = None) -> None:
        data = await state.get_data()
        brand, style, prev = data.get("brand", ""), data.get("style", ""), data.get("svg")
        await state.set_state(LogoStates.done)
        key = await gemini.resolve_key(db, bot.id)
        wait = await target.answer("⏳ Logotip yaratilmoqda, biroz kuting...")

        if prev and instruction:
            prompt = (f"Here is the current logo SVG:\n{prev}\n\nApply this change: {instruction}\n"
                      f"Brand name: {brand}. Return the complete updated SVG only.")
        else:
            prompt = (f"Brand name: {brand}\nIndustry/style/colors: {style or 'free choice'}\n"
                      f"Design a professional logo for this brand. Variation seed: {random.randint(1, 99999)}. "
                      f"Return the SVG only.")
        try:
            await bot.send_chat_action(target.chat.id, "upload_photo")
            raw = await gemini.generate(key, prompt, system_instruction=LOGO_SYSTEM, temperature=1.0, timeout=120)
        except GeminiError as e:
            await safe_edit(wait, f"❌ {esc(e)}", retry_logo_kb())
            return
        svg = extract_svg(raw)
        if not svg:
            await safe_edit(wait, "❌ AI to'g'ri SVG qaytarmadi. Qayta urinib ko'ring.", retry_logo_kb())
            return

        await state.update_data(svg=svg)
        png = await svg_to_png(svg)
        try:
            await wait.delete()
        except TelegramAPIError:
            pass
        try:
            if png:
                await target.answer_photo(BufferedInputFile(png, "logo.png"), caption=f"🎨 <b>{esc(brand)}</b> logotipi")
            await target.answer_document(
                BufferedInputFile(svg.encode("utf-8"), f"logo.svg"),
                caption=("📐 Vektor (SVG) fayl — brauzer, Figma yoki Canva'da ochishingiz mumkin."
                         if png else
                         f"🎨 <b>{esc(brand)}</b> logotipi (SVG). Brauzer, Figma yoki Canva'da oching."),
                reply_markup=logo_result_kb())
        except TelegramAPIError:
            logger.exception("Logotip yuborishda xatolik")
            await target.answer("⚠️ Faylni yuborib bo'lmadi.", reply_markup=retry_logo_kb())

    # ---------------- Savol-javob ----------------
    @router.callback_query(F.data == "logo:qa")
    async def cb_qa(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(LogoStates.qa)
        await state.update_data(history=[])
        await cb.message.answer("❓ Logotip va dizayn haqida istalgan savolingizni yozing.\n(Chiqish: /cancel)",
                                reply_markup=logo_nav_kb())

    @router.message(LogoStates.qa, TEXT)
    async def qa_chat(message: Message, state: FSMContext, bot: Bot, db, gemini: GeminiService) -> None:
        key = await gemini.resolve_key(db, bot.id)
        history: list = (await state.get_data()).get("history", [])
        history.append({"role": "user", "parts": [message.text[:2000]]})
        try:
            await bot.send_chat_action(message.chat.id, "typing")
            answer = await gemini.generate(key, history, system_instruction=QA_SYSTEM)
        except GeminiError as e:
            history.pop()
            await message.answer(f"❌ {esc(e)}")
            return
        history.append({"role": "model", "parts": [answer[:3000]]})
        await state.update_data(history=history[-12:])
        await reply_long(message, answer, reply_markup=logo_nav_kb())

    return router
