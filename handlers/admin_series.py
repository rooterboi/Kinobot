"""Admin panel: seriallar va qismlarni boshqarish."""
from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from filters import TEXT, AdminFilter
from keyboards import (back_kb, confirm_series_delete_kb, edit_fields_kb, episodes_done_kb, open_bot_kb,
                       series_menu_kb)
from states import AddEpisode, AddSeries, DeleteEpisode, DeleteSeries, EditSeries
from utils import build_series_post_text, esc, make_hashtags, safe_edit

logger = logging.getLogger(__name__)

FLOW = [
    ("title", AddSeries.title, "📺 Serial <b>nomini</b> kiriting:"),
    ("year", AddSeries.year, "📅 <b>Yilini</b> kiriting (masalan: 2024):"),
    ("quality", AddSeries.quality, "🖥 <b>Sifatini</b> kiriting (masalan: 1080p HD):"),
    ("country", AddSeries.country, "🗽 <b>Davlatini</b> kiriting:"),
    ("language", AddSeries.language, "🇺🇿 <b>Tilini</b> kiriting (masalan: O'zbek tilida):"),
    ("genre", AddSeries.genre, "🍿 <b>Janrlarini</b> kiriting (vergul bilan: Drama, Detektiv):"),
]
LABELS = {"title": "nomi", "year": "yili", "quality": "sifati", "country": "davlati",
          "language": "tili", "genre": "janri", "code": "kodi"}


def create_series_admin_router() -> Router:
    router = Router()
    router.message.filter(AdminFilter())
    router.callback_query.filter(AdminFilter())

    # ---------------- Menyu ----------------
    @router.callback_query(F.data == "adm:series")
    async def cb_series(cb: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await cb.answer()
        await safe_edit(cb.message, "📺 <b>Seriallarni boshqarish</b>", series_menu_kb())

    @router.callback_query(F.data == "ser:list")
    async def cb_list(cb: CallbackQuery, bot: Bot, db) -> None:
        await cb.answer()
        items = await db.list_series(bot.id, 40)
        if not items:
            text = "📋 Hozircha seriallar yo'q."
        else:
            text = "📋 <b>So'nggi seriallar:</b>\n\n" + "\n".join(
                f"<code>{esc(s['code'])}</code> — {esc(s['title'])} ({esc(s['year'])}) • {s['eps']} qism"
                for s in items)
        await safe_edit(cb.message, text, back_kb("adm:series"))

    # ---------------- Serial qo'shish ----------------
    @router.callback_query(F.data == "ser:add")
    async def cb_add(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.clear()
        await state.set_state(FLOW[0][1])
        await cb.message.answer(FLOW[0][2] + "\n\nBekor qilish: /cancel")

    @router.message(StateFilter(AddSeries.title, AddSeries.year, AddSeries.quality, AddSeries.country,
                                AddSeries.language, AddSeries.genre), TEXT)
    async def add_fields(message: Message, state: FSMContext, bot: Bot, db) -> None:
        current = await state.get_state()
        idx = next(i for i, (_, st, _) in enumerate(FLOW) if st.state == current)
        field = FLOW[idx][0]
        value = message.text.strip()[:200]
        if field == "year" and not re.fullmatch(r"\d{4}", value):
            await message.answer("⚠️ Yil 4 xonali raqam bo'lishi kerak (masalan: 2024).")
            return
        if field == "genre":
            value = make_hashtags(value)
        await state.update_data(**{field: value})
        if idx + 1 < len(FLOW):
            await state.set_state(FLOW[idx + 1][1])
            await message.answer(FLOW[idx + 1][2])
        else:
            await state.set_state(AddSeries.code)
            nxt = await db.next_code(bot.id)
            await message.answer(f"🔢 Serial uchun <b>raqamli kod</b> kiriting (tavsiya: <code>{nxt}</code>):")

    @router.message(AddSeries.code, TEXT)
    async def add_code(message: Message, state: FSMContext, bot: Bot, db) -> None:
        code = message.text.strip()
        if not re.fullmatch(r"\d{1,12}", code):
            await message.answer("⚠️ Kod faqat raqamlardan iborat bo'lishi kerak.")
            return
        data = await state.get_data()
        series = {k: data.get(k) for k in ("title", "year", "quality", "country", "language", "genre")}
        series["code"] = code
        if await db.code_taken(bot.id, code) or await db.add_series(bot.id, series) is None:
            await message.answer("⚠️ Bu kod band (kino yoki serialda). Boshqa kod kiriting:")
            return
        await state.clear()
        result = (f"✅ Serial saqlandi!\n📺 <b>{esc(series['title'])}</b> — kod: <code>{code}</code>\n"
                  f"Endi «➕ Qism qo'shish» orqali qismlarni yuklang.")
        chat_id = await db.get_setting(bot.id, "post_channel")
        if chat_id:
            try:
                username = (await bot.me()).username
                await bot.send_message(int(chat_id), build_series_post_text(series, username),
                                       reply_markup=open_bot_kb(username))
                result += "\n📣 Kanalga e'lon joylandi."
            except TelegramAPIError as e:
                logger.warning("Kanalga serial postini joylab bo'lmadi: %s", e)
                result += "\n⚠️ Kanalga post joylanmadi (bot kanalda admin ekanini tekshiring)."
        await message.answer(result, reply_markup=back_kb("adm:series"))

    # ---------------- Qism qo'shish ----------------
    @router.callback_query(F.data == "ser:ep")
    async def cb_ep(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.clear()
        await state.set_state(AddEpisode.code)
        await cb.message.answer("🔢 Qism qo'shiladigan <b>serial kodini</b> yuboring:")

    @router.message(AddEpisode.code, TEXT)
    async def ep_code(message: Message, state: FSMContext, bot: Bot, db) -> None:
        series = await db.get_series(bot.id, message.text.strip())
        if not series:
            await message.answer("❌ Bunday kodli serial topilmadi. Qayta kiriting yoki /cancel.")
            return
        count = len(await db.list_episode_numbers(series["id"]))
        await state.update_data(series_id=series["id"], title=series["title"])
        await state.set_state(AddEpisode.video)
        await message.answer(
            f"📤 <b>{esc(series['title'])}</b> (hozir {count} qism)\n\nQism videolarini ketma-ket yuboring — "
            f"har biri avtomatik keyingi raqam bilan saqlanadi. Tugagach «✅ Tugatish» ni bosing.",
            reply_markup=episodes_done_kb())

    @router.message(AddEpisode.video, F.video | F.document)
    async def ep_video(message: Message, state: FSMContext, db) -> None:
        data = await state.get_data()
        if message.video:
            file_id, ftype = message.video.file_id, "video"
        else:
            file_id, ftype = message.document.file_id, "document"
        try:
            number = await db.add_episode(data["series_id"], file_id, ftype)
        except Exception:  # noqa: BLE001
            logger.exception("Qism saqlashda xatolik")
            await message.answer("❌ Qismni saqlab bo'lmadi. Qayta yuboring.")
            return
        await message.answer(f"✅ <b>{number}-qism</b> saqlandi. Keyingisini yuboring.", reply_markup=episodes_done_kb())

    @router.message(AddEpisode.video, ~F.text.startswith("/"))
    async def ep_video_wrong(message: Message) -> None:
        await message.answer("⚠️ Iltimos, video yoki fayl yuboring (yoki «✅ Tugatish»).")

    @router.callback_query(F.data == "ser:epdone")
    async def ep_done(cb: CallbackQuery, state: FSMContext, db) -> None:
        data = await state.get_data()
        await state.clear()
        await cb.answer("Tugatildi")
        total = len(await db.list_episode_numbers(data["series_id"])) if data.get("series_id") else 0
        await safe_edit(cb.message, f"✅ Tugatildi. Serialda jami <b>{total}</b> ta qism bor.", back_kb("adm:series"))

    # ---------------- Qismni o'chirish ----------------
    @router.callback_query(F.data == "ser:epdel")
    async def cb_epdel(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.clear()
        await state.set_state(DeleteEpisode.code)
        await cb.message.answer("🔢 Serial <b>kodini</b> yuboring:")

    @router.message(DeleteEpisode.code, TEXT)
    async def epdel_code(message: Message, state: FSMContext, bot: Bot, db) -> None:
        series = await db.get_series(bot.id, message.text.strip())
        if not series:
            await message.answer("❌ Bunday kodli serial topilmadi. Qayta kiriting yoki /cancel.")
            return
        numbers = await db.list_episode_numbers(series["id"])
        if not numbers:
            await state.clear()
            await message.answer("ℹ️ Bu serialda qismlar yo'q.", reply_markup=back_kb("adm:series"))
            return
        await state.update_data(series_id=series["id"])
        await state.set_state(DeleteEpisode.number)
        await message.answer(f"🎞 Mavjud qismlar: {', '.join(map(str, numbers))}\n\nO'chiriladigan <b>qism raqamini</b> yuboring:")

    @router.message(DeleteEpisode.number, TEXT)
    async def epdel_number(message: Message, state: FSMContext, db) -> None:
        if not message.text.strip().isdigit():
            await message.answer("⚠️ Faqat raqam yuboring.")
            return
        data = await state.get_data()
        ok = await db.delete_episode(data["series_id"], int(message.text.strip()))
        await state.clear()
        await message.answer("✅ Qism o'chirildi." if ok else "❌ Bunday qism topilmadi.",
                             reply_markup=back_kb("adm:series"))

    # ---------------- Serialni o'chirish ----------------
    @router.callback_query(F.data == "ser:del")
    async def cb_del(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.clear()
        await state.set_state(DeleteSeries.code)
        await cb.message.answer("🗑 O'chiriladigan serial <b>kodini</b> yuboring:")

    @router.message(DeleteSeries.code, TEXT)
    async def del_code(message: Message, state: FSMContext, bot: Bot, db) -> None:
        series = await db.get_series(bot.id, message.text.strip())
        if not series:
            await message.answer("❌ Bunday kodli serial topilmadi. Qayta kiriting yoki /cancel.")
            return
        await state.clear()
        count = len(await db.list_episode_numbers(series["id"]))
        await message.answer(f"❓ <b>{esc(series['title'])}</b> (kod: <code>{esc(series['code'])}</code>) "
                             f"va uning {count} ta qismi o'chirilsinmi?",
                             reply_markup=confirm_series_delete_kb(series["code"]))

    @router.callback_query(F.data.startswith("ser:delok:"))
    async def del_ok(cb: CallbackQuery, bot: Bot, db) -> None:
        deleted = await db.delete_series(bot.id, cb.data.split(":", 2)[2])
        await cb.answer("✅ O'chirildi" if deleted else "Topilmadi", show_alert=not deleted)
        await safe_edit(cb.message, "✅ Serial o'chirildi." if deleted else "❌ Serial topilmadi.",
                        back_kb("adm:series"))

    # ---------------- Tahrirlash ----------------
    @router.callback_query(F.data == "ser:edit")
    async def cb_edit(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.clear()
        await state.set_state(EditSeries.code)
        await cb.message.answer("✏️ Tahrirlanadigan serial <b>kodini</b> yuboring:")

    @router.message(EditSeries.code, TEXT)
    async def edit_code(message: Message, state: FSMContext, bot: Bot, db) -> None:
        code = message.text.strip()
        series = await db.get_series(bot.id, code)
        if not series:
            await message.answer("❌ Bunday kodli serial topilmadi. Qayta kiriting yoki /cancel.")
            return
        await state.update_data(code=code)
        await state.set_state(EditSeries.field)
        await message.answer(f"✏️ <b>{esc(series['title'])}</b>\nQaysi maydonni o'zgartiramiz?",
                             reply_markup=edit_fields_kb("ser:ef"))

    @router.callback_query(EditSeries.field, F.data.startswith("ser:ef:"))
    async def edit_field(cb: CallbackQuery, state: FSMContext) -> None:
        field = cb.data.split(":", 2)[2]
        if field not in LABELS:
            await cb.answer("Noto'g'ri maydon", show_alert=True)
            return
        await cb.answer()
        await state.update_data(field=field)
        await state.set_state(EditSeries.value)
        await cb.message.answer(f"Yangi <b>{LABELS[field]}</b>ni kiriting:")

    @router.message(EditSeries.value, TEXT)
    async def edit_value(message: Message, state: FSMContext, bot: Bot, db) -> None:
        data = await state.get_data()
        field, code = data["field"], data["code"]
        value = message.text.strip()[:200]
        if field == "year" and not re.fullmatch(r"\d{4}", value):
            await message.answer("⚠️ Yil 4 xonali raqam bo'lishi kerak.")
            return
        if field == "code":
            if not re.fullmatch(r"\d{1,12}", value):
                await message.answer("⚠️ Kod faqat raqamlardan iborat bo'lishi kerak.")
                return
            if await db.code_taken(bot.id, value):
                await message.answer("⚠️ Bu kod band. Boshqa kod kiriting yoki /cancel.")
                return
        if field == "genre":
            value = make_hashtags(value)
        if not await db.update_series_field(bot.id, code, field, value):
            await message.answer("⚠️ Yangilab bo'lmadi. Qayta kiriting yoki /cancel.")
            return
        await state.clear()
        await message.answer("✅ Yangilandi.", reply_markup=back_kb("adm:series"))

    return router
