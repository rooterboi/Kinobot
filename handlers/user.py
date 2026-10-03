"""Oddiy foydalanuvchi funksiyalari: kod bo'yicha kino, qidiruv, Kino AI."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from filters import TEXT
from handlers.common import SUB_TEXT, subscription_markup
from aiogram.types import CallbackQuery
from keyboards import (BTN_AI, BTN_EXIT, episode_nav_kb, episodes_kb, exit_kb, user_menu_kb)
from services.gemini import GeminiError, GeminiService
from states import AIStates
from utils import build_caption, build_series_caption, esc, reply_long

logger = logging.getLogger(__name__)

AI_SYSTEM = (
    "Siz kino botning AI yordamchisisiz. Foydalanuvchi bilan o'zbek tilida (u boshqa tilda yozsa, shu tilda) "
    "do'stona va qisqa muloqot qiling. Foydalanuvchiga kino tavsiya qilganda, quyidagi bot bazasidagi "
    "kinolardan foydalaning va ularning KODINI aniq ayting. Agar bazada mos kino bo'lmasa, buni ochiq ayting "
    "va umumiy tavsiya bering. Kodlarni o'ylab topmang.\n\nBAZADAGI KINOLAR (kod — nom (yil) janr):\n{catalog}"
)


def create_user_router() -> Router:
    router = Router()

    @router.message(F.text == BTN_AI)
    async def ai_enter(message: Message, state: FSMContext, bot: Bot, db, gemini: GeminiService, config) -> None:
        if not await gemini.resolve_key(db, bot.id):
            await message.answer("⚠️ AI hozircha faollashtirilmagan. Admin Gemini API kalitini kiritishi kerak.")
            return
        await state.set_state(AIStates.chat)
        await state.update_data(history=[])
        await message.answer(
            "🤖 <b>Kino AI</b> yoqildi!\nJanr, kayfiyat yoki kino nomi bo'yicha so'rang — masalan: "
            "<i>«Jangari va hayajonli film tavsiya qil»</i>.\n\nChiqish: «❌ Chiqish»", reply_markup=exit_kb())

    @router.message(AIStates.chat, F.text == BTN_EXIT)
    async def ai_exit(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("👋 AI rejimidan chiqdingiz. Kino kodini yuborishingiz mumkin.",
                             reply_markup=user_menu_kb())

    @router.message(AIStates.chat, TEXT)
    async def ai_chat(message: Message, state: FSMContext, bot: Bot, db, gemini: GeminiService) -> None:
        key = await gemini.resolve_key(db, bot.id)
        movies = await db.list_movies(bot.id, 80)
        series_list = await db.list_series(bot.id, 40)
        catalog = "\n".join(
            [f"{m['code']} — {m['title']} ({m['year']}) {m['genre']}" for m in movies]
            + [f"{s['code']} — {s['title']} ({s['year']}) {s['genre']} [serial, {s['eps']} qism]"
               for s in series_list]) or "(baza hozircha bo'sh)"
        data = await state.get_data()
        history: list = data.get("history", [])
        history.append({"role": "user", "parts": [message.text[:2000]]})
        try:
            await bot.send_chat_action(message.chat.id, "typing")
            answer = await gemini.generate(key, history, system_instruction=AI_SYSTEM.format(catalog=catalog))
        except GeminiError as e:
            history.pop()
            await message.answer(f"❌ {esc(e)}")
            return
        history.append({"role": "model", "parts": [answer[:3000]]})
        await state.update_data(history=history[-12:])
        await reply_long(message, answer)

    @router.message(StateFilter(None), F.text.regexp(r"^\d{1,12}$"))
    async def by_code(message: Message, bot: Bot, db, config) -> None:
        markup = await subscription_markup(bot, db, config, message.from_user.id)
        if markup:
            await message.answer(SUB_TEXT, reply_markup=markup)
            return
        code = message.text.strip()
        movie = await db.get_movie(bot.id, code)
        if not movie:
            series = await db.get_series(bot.id, code)
            if series:
                await _send_series(message, bot, db, series)
            else:
                await message.answer("❌ Bunday kodli kino yoki serial topilmadi. Kodni tekshirib qayta yuboring.")
            return
        username = (await bot.me()).username
        caption = build_caption(movie, username)
        try:
            if movie["file_type"] == "video":
                await message.answer_video(movie["file_id"], caption=caption)
            else:
                await message.answer_document(movie["file_id"], caption=caption)
            await db.inc_views(bot.id, movie["code"])
        except TelegramAPIError:
            logger.exception("Kino yuborishda xatolik")
            await message.answer("⚠️ Kinoni yuborib bo'lmadi. Keyinroq urinib ko'ring.")

    @router.message(StateFilter(None), TEXT)
    async def search(message: Message, bot: Bot, db, config) -> None:
        query = message.text.strip()
        if len(query) < 2:
            return
        markup = await subscription_markup(bot, db, config, message.from_user.id)
        if markup:
            await message.answer(SUB_TEXT, reply_markup=markup)
            return
        found = await db.search_movies(bot.id, query)
        found_series = await db.search_series(bot.id, query)
        if not found and not found_series:
            await message.answer("🔍 Hech narsa topilmadi. Raqamli kod yuboring yoki «🤖 Kino AI» dan so'rang.")
            return
        lines = [f"🔍 <b>Topilgan kinolar:</b>"]
        lines += [f"🎬 {esc(m['title'])} ({esc(m['year'])}) — kod: <code>{esc(m['code'])}</code>" for m in found]
        lines += [f"📺 {esc(s['title'])} ({esc(s['year'])}) — serial kodi: <code>{esc(s['code'])}</code>"
                  for s in found_series]
        await message.answer("\n".join(lines))

    # ---------------- Seriallar ----------------
    async def _send_series(message: Message, bot: Bot, db, series: dict) -> None:
        numbers = await db.list_episode_numbers(series["id"])
        caption = build_series_caption(series, (await bot.me()).username, len(numbers))
        if not numbers:
            await message.answer(caption.split("\n\n")[0] + "\n\n⏳ Qismlar tez orada qo'shiladi.")
            return
        await message.answer(caption, reply_markup=episodes_kb(series["id"], numbers, 0))

    async def _sub_ok(cb: CallbackQuery, bot: Bot, db, config) -> bool:
        markup = await subscription_markup(bot, db, config, cb.from_user.id)
        if markup:
            await cb.answer("❌ Avval kanallarga a'zo bo'ling!", show_alert=True)
            if cb.message:
                await cb.message.answer(SUB_TEXT, reply_markup=markup)
            return False
        return True

    @router.callback_query(F.data == "noop")
    async def cb_noop(cb: CallbackQuery) -> None:
        await cb.answer()

    @router.callback_query(F.data.startswith("epl:"))
    async def cb_ep_page(cb: CallbackQuery, bot: Bot, db) -> None:
        try:
            _, sid, page = cb.data.split(":")
            numbers = await db.list_episode_numbers(int(sid))
            await cb.answer()
            await cb.message.edit_reply_markup(reply_markup=episodes_kb(int(sid), numbers, int(page)))
        except (ValueError, TelegramAPIError):
            await cb.answer()

    @router.callback_query(F.data.startswith("epm:"))
    async def cb_ep_menu(cb: CallbackQuery, bot: Bot, db, config) -> None:
        if not await _sub_ok(cb, bot, db, config):
            return
        series = await db.get_series_by_id(int(cb.data.split(":")[1]))
        await cb.answer()
        if series and series["bot_id"] == bot.id:
            await _send_series(cb.message, bot, db, series)

    @router.callback_query(F.data.startswith("ep:"))
    async def cb_episode(cb: CallbackQuery, bot: Bot, db, config) -> None:
        if not await _sub_ok(cb, bot, db, config):
            return
        try:
            _, sid, num = cb.data.split(":")
            series = await db.get_series_by_id(int(sid))
            ep = await db.get_episode(int(sid), int(num)) if series else None
        except ValueError:
            await cb.answer("Xatolik", show_alert=True)
            return
        if not series or series["bot_id"] != bot.id or not ep:
            await cb.answer("❌ Qism topilmadi", show_alert=True)
            return
        await cb.answer()
        numbers = await db.list_episode_numbers(series["id"])
        caption = (f"📺 <b>{esc(series['title'])}</b> — <b>{ep['number']}-qism</b>\n\n"
                   f"🤖 @{esc((await bot.me()).username)}")
        kb = episode_nav_kb(series["id"], ep["number"], numbers)
        try:
            if ep["file_type"] == "video":
                await cb.message.answer_video(ep["file_id"], caption=caption, reply_markup=kb)
            else:
                await cb.message.answer_document(ep["file_id"], caption=caption, reply_markup=kb)
            await db.inc_series_views(series["id"])
        except TelegramAPIError:
            logger.exception("Qism yuborishda xatolik")
            await cb.message.answer("⚠️ Qismni yuborib bo'lmadi. Keyinroq urinib ko'ring.")

    return router
