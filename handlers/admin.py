"""To'liq admin panel."""
from __future__ import annotations

import asyncio
import logging
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import (TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from filters import TEXT, AdminFilter
from keyboards import (admin_menu_kb, back_kb, broadcast_kb, channels_kb, confirm_delete_kb, edit_fields_kb,
                       gemini_kb, movies_menu_kb, open_bot_kb, pin_kb, postch_kb)
from services.gemini import GeminiError, GeminiService
from states import (AddMovie, BroadcastStates, ChannelStates, DeleteMovie, EditMovie, SettingsStates)
from utils import (build_post_text, esc, get_chat_link, hash_pin, make_hashtags, mask_key, resolve_chat,
                   safe_edit, try_delete)

logger = logging.getLogger(__name__)

FIELD_FLOW = [
    ("title", AddMovie.title, "🎬 Kino <b>nomini</b> kiriting:"),
    ("year", AddMovie.year, "📅 <b>Yilini</b> kiriting (masalan: 2024):"),
    ("quality", AddMovie.quality, "🖥 <b>Sifatini</b> kiriting (masalan: 1080p HD):"),
    ("country", AddMovie.country, "🗽 <b>Davlatini</b> kiriting:"),
    ("language", AddMovie.language, "🇺🇿 <b>Tilini</b> kiriting (masalan: O'zbek tilida):"),
    ("genre", AddMovie.genre, "🍿 <b>Janrlarini</b> kiriting (vergul bilan: Jangari, Drama):"),
]
FIELD_LABELS = {"title": "nomi", "year": "yili", "quality": "sifati", "country": "davlati",
                "language": "tili", "genre": "janri", "code": "kodi"}

_background: set[asyncio.Task] = set()


def _markup_from_buttons(buttons: list[list[str]]) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    b = InlineKeyboardBuilder()
    for text, url in buttons:
        b.button(text=text, url=url)
    b.adjust(1)
    return b.as_markup()


async def _broadcast(bot: Bot, db, admin_chat: int, src_chat: int, src_msg: int,
                     buttons: list[list[str]], forward: bool) -> None:
    users = await db.all_user_ids(bot.id)
    markup = _markup_from_buttons(buttons)
    ok = fail = 0

    async def send(uid: int) -> None:
        if forward:
            await bot.forward_message(uid, src_chat, src_msg)
        else:
            await bot.copy_message(uid, src_chat, src_msg, reply_markup=markup)

    for uid in users:
        try:
            await send(uid)
            ok += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await send(uid)
                ok += 1
            except TelegramAPIError:
                fail += 1
        except TelegramForbiddenError:
            fail += 1
        except TelegramAPIError:
            fail += 1
        except Exception:  # noqa: BLE001
            logger.exception("Broadcast xatosi")
            fail += 1
        await asyncio.sleep(0.05)
    try:
        await bot.send_message(admin_chat, f"📨 <b>Reklama yakunlandi</b>\n\n✅ Yuborildi: {ok}\n🚫 Yetib bormadi: {fail}")
    except TelegramAPIError:
        pass


def create_admin_router(is_main: bool) -> Router:
    router = Router()
    router.message.filter(AdminFilter())
    router.callback_query.filter(AdminFilter())

    # ---------------- Asosiy menyu ----------------
    @router.message(Command("admin"))
    async def cmd_admin(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("🛠 <b>Admin panel</b>", reply_markup=admin_menu_kb(is_main))

    @router.callback_query(F.data == "adm:menu")
    async def cb_menu(cb: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await cb.answer()
        await safe_edit(cb.message, "🛠 <b>Admin panel</b>", admin_menu_kb(is_main))

    @router.callback_query(F.data == "adm:close")
    async def cb_close(cb: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await cb.answer()
        if cb.message:
            await try_delete(cb.message)

    @router.callback_query(F.data == "adm:stats")
    async def cb_stats(cb: CallbackQuery, bot: Bot, db) -> None:
        await cb.answer()
        s = await db.stats(bot.id)
        text = (
            "📊 <b>Statistika</b>\n\n"
            f"👥 Jami foydalanuvchilar: <b>{s['users']}</b>\n"
            f"🔥 Bugun faol: <b>{s['active_today']}</b>\n"
            f"🆕 Bugun qo'shilgan: <b>{s['new_today']}</b>\n"
            f"🎬 Yuklangan kinolar: <b>{s['movies']}</b>\n"
            f"📺 Seriallar: <b>{s['series']}</b> ({s['episodes']} qism)\n"
            f"👁 Jami ko'rishlar: <b>{s['views']}</b>\n"
            f"📢 Majburiy kanallar: <b>{s['channels']}</b>"
        )
        await safe_edit(cb.message, text, back_kb())

    # ---------------- Kinolar ----------------
    @router.callback_query(F.data == "adm:movies")
    async def cb_movies(cb: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await cb.answer()
        await safe_edit(cb.message, "🎬 <b>Kinolarni boshqarish</b>", movies_menu_kb())

    @router.callback_query(F.data == "mov:list")
    async def cb_list(cb: CallbackQuery, bot: Bot, db) -> None:
        await cb.answer()
        movies = await db.list_movies(bot.id, 40)
        if not movies:
            text = "📋 Hozircha kinolar yo'q."
        else:
            text = "📋 <b>So'nggi kinolar:</b>\n\n" + "\n".join(
                f"<code>{esc(m['code'])}</code> — {esc(m['title'])} ({esc(m['year'])})" for m in movies)
        await safe_edit(cb.message, text, back_kb("adm:movies"))

    # --- qo'shish ---
    @router.callback_query(F.data == "mov:add")
    async def cb_add(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.clear()
        await state.set_state(AddMovie.video)
        await cb.message.answer("🎞 Kino <b>videosini</b> (yoki faylini) yuboring.\n\nBekor qilish: /cancel")

    @router.message(AddMovie.video, F.video | F.document)
    async def add_video(message: Message, state: FSMContext) -> None:
        if message.video:
            file_id, ftype = message.video.file_id, "video"
        else:
            file_id, ftype = message.document.file_id, "document"
        await state.update_data(file_id=file_id, file_type=ftype)
        await state.set_state(FIELD_FLOW[0][1])
        await message.answer(FIELD_FLOW[0][2])

    @router.message(AddMovie.video, ~F.text.startswith("/"))
    async def add_video_wrong(message: Message) -> None:
        await message.answer("⚠️ Iltimos, video yoki fayl yuboring.")

    @router.message(StateFilter(AddMovie.title, AddMovie.year, AddMovie.quality, AddMovie.country,
                                AddMovie.language, AddMovie.genre), TEXT)
    async def add_fields(message: Message, state: FSMContext, bot: Bot, db) -> None:
        current = await state.get_state()
        idx = next(i for i, (_, st, _) in enumerate(FIELD_FLOW) if st.state == current)
        field = FIELD_FLOW[idx][0]
        value = message.text.strip()[:200]
        if field == "year" and not re.fullmatch(r"\d{4}", value):
            await message.answer("⚠️ Yil 4 xonali raqam bo'lishi kerak (masalan: 2024).")
            return
        if field == "genre":
            value = make_hashtags(value)
        await state.update_data(**{field: value})
        if idx + 1 < len(FIELD_FLOW):
            await state.set_state(FIELD_FLOW[idx + 1][1])
            await message.answer(FIELD_FLOW[idx + 1][2])
        else:
            await state.set_state(AddMovie.code)
            nxt = await db.next_code(bot.id)
            await message.answer(f"🔢 Kino uchun <b>raqamli kod</b> kiriting (tavsiya: <code>{nxt}</code>):")

    @router.message(AddMovie.code, TEXT)
    async def add_code(message: Message, state: FSMContext, bot: Bot, db) -> None:
        code = message.text.strip()
        if not re.fullmatch(r"\d{1,12}", code):
            await message.answer("⚠️ Kod faqat raqamlardan iborat bo'lishi kerak.")
            return
        data = await state.get_data()
        movie = {**{k: data.get(k) for k in ("file_id", "file_type", "title", "year", "quality",
                                             "country", "language", "genre")}, "code": code}
        if await db.code_taken(bot.id, code) or not await db.add_movie(bot.id, movie):
            await message.answer("⚠️ Bu kod band. Boshqa kod kiriting:")
            return
        await state.clear()
        result = f"✅ Kino saqlandi!\n🎬 <b>{esc(movie['title'])}</b> — kod: <code>{code}</code>"

        chat_id = await db.get_setting(bot.id, "post_channel")
        if chat_id:
            try:
                username = (await bot.me()).username
                await bot.send_message(int(chat_id), build_post_text(movie, username),
                                       reply_markup=open_bot_kb(username))
                result += "\n📣 Kanalga e'lon joylandi."
            except TelegramAPIError as e:
                logger.warning("Kanalga post joylab bo'lmadi: %s", e)
                result += "\n⚠️ Kanalga post joylanmadi (bot kanalda admin ekanini tekshiring)."
        else:
            result += "\nℹ️ Post kanali ulanmagan (Admin panel → 📣 Post kanali)."
        await message.answer(result)

    # --- o'chirish ---
    @router.callback_query(F.data == "mov:del")
    async def cb_del(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(DeleteMovie.code)
        await cb.message.answer("🗑 O'chiriladigan kino <b>kodini</b> yuboring:")

    @router.message(DeleteMovie.code, TEXT)
    async def del_code(message: Message, state: FSMContext, bot: Bot, db) -> None:
        movie = await db.get_movie(bot.id, message.text.strip())
        if not movie:
            await message.answer("❌ Bunday kodli kino topilmadi. Qayta kiriting yoki /cancel.")
            return
        await state.clear()
        await message.answer(f"❓ <b>{esc(movie['title'])}</b> (kod: <code>{esc(movie['code'])}</code>) "
                             "o'chirilsinmi?", reply_markup=confirm_delete_kb(movie["code"]))

    @router.callback_query(F.data.startswith("mov:delok:"))
    async def del_ok(cb: CallbackQuery, bot: Bot, db) -> None:
        code = cb.data.split(":", 2)[2]
        deleted = await db.delete_movie(bot.id, code)
        await cb.answer("✅ O'chirildi" if deleted else "Topilmadi", show_alert=not deleted)
        await safe_edit(cb.message, "✅ Kino o'chirildi." if deleted else "❌ Kino topilmadi.", back_kb("adm:movies"))

    # --- tahrirlash ---
    @router.callback_query(F.data == "mov:edit")
    async def cb_edit(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(EditMovie.code)
        await cb.message.answer("✏️ Tahrirlanadigan kino <b>kodini</b> yuboring:")

    @router.message(EditMovie.code, TEXT)
    async def edit_code(message: Message, state: FSMContext, bot: Bot, db) -> None:
        code = message.text.strip()
        movie = await db.get_movie(bot.id, code)
        if not movie:
            await message.answer("❌ Bunday kodli kino topilmadi. Qayta kiriting yoki /cancel.")
            return
        await state.update_data(code=code)
        await state.set_state(EditMovie.field)
        await message.answer(f"✏️ <b>{esc(movie['title'])}</b>\nQaysi maydonni o'zgartiramiz?",
                             reply_markup=edit_fields_kb())

    @router.callback_query(EditMovie.field, F.data.startswith("mov:ef:"))
    async def edit_field(cb: CallbackQuery, state: FSMContext) -> None:
        field = cb.data.split(":", 2)[2]
        if field not in FIELD_LABELS:
            await cb.answer("Noto'g'ri maydon", show_alert=True)
            return
        await cb.answer()
        await state.update_data(field=field)
        await state.set_state(EditMovie.value)
        await cb.message.answer(f"Yangi <b>{FIELD_LABELS[field]}</b>ni kiriting:")

    @router.message(EditMovie.value, TEXT)
    async def edit_value(message: Message, state: FSMContext, bot: Bot, db) -> None:
        data = await state.get_data()
        field, code = data["field"], data["code"]
        value = message.text.strip()[:200]
        if field == "year" and not re.fullmatch(r"\d{4}", value):
            await message.answer("⚠️ Yil 4 xonali raqam bo'lishi kerak.")
            return
        if field == "code" and not re.fullmatch(r"\d{1,12}", value):
            await message.answer("⚠️ Kod faqat raqamlardan iborat bo'lishi kerak.")
            return
        if field == "genre":
            value = make_hashtags(value)
        if field == "code" and await db.code_taken(bot.id, value):
            await message.answer("⚠️ Bu kod band (kino yoki serialda). Boshqa kod kiriting yoki /cancel.")
            return
        ok = await db.update_movie_field(bot.id, code, field, value)
        if not ok:
            await message.answer("⚠️ Yangilab bo'lmadi (kod band bo'lishi mumkin). Qayta kiriting yoki /cancel.")
            return
        await state.clear()
        await message.answer("✅ Yangilandi.", reply_markup=back_kb("adm:movies"))

    # ---------------- Majburiy obuna ----------------
    async def _show_channels(cb_message: Message | None, bot: Bot, db) -> None:
        channels = await db.list_channels(bot.id)
        text = "📢 <b>Majburiy obuna kanallari</b>\n\n" + (
            "\n".join(f"• {esc(c['title'])}" for c in channels) if channels else "Hozircha kanal yo'q.")
        await safe_edit(cb_message, text, channels_kb(channels))

    @router.callback_query(F.data == "adm:channels")
    async def cb_channels(cb: CallbackQuery, state: FSMContext, bot: Bot, db) -> None:
        await state.clear()
        await cb.answer()
        await _show_channels(cb.message, bot, db)

    @router.callback_query(F.data == "ch:add")
    async def cb_ch_add(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(ChannelStates.add_sub)
        await cb.message.answer("➕ Kanal <b>@username</b> yoki ID sini yuboring (yoki kanaldan post forward qiling).\n"
                                "⚠️ Bot kanalda <b>admin</b> bo'lishi shart.\n\nBekor qilish: /cancel")

    @router.message(ChannelStates.add_sub)
    async def ch_add_got(message: Message, state: FSMContext, bot: Bot, db) -> None:
        try:
            chat = await resolve_chat(bot, message)
            link = await get_chat_link(bot, chat)
        except ValueError as e:
            await message.answer(f"❌ {esc(e)}\n\nQayta yuboring yoki /cancel.")
            return
        if not await db.add_channel(bot.id, chat.id, chat.title or str(chat.id), link):
            await message.answer("⚠️ Bu kanal allaqachon qo'shilgan.")
        else:
            await message.answer(f"✅ <b>{esc(chat.title)}</b> majburiy obunaga qo'shildi.",
                                 reply_markup=back_kb("adm:channels"))
        await state.clear()

    @router.callback_query(F.data.startswith("ch:del:"))
    async def cb_ch_del(cb: CallbackQuery, bot: Bot, db) -> None:
        await db.remove_channel(bot.id, int(cb.data.split(":")[2]))
        await cb.answer("🗑 O'chirildi")
        await _show_channels(cb.message, bot, db)

    # ---------------- Post kanali (avto-post) ----------------
    async def _show_postch(cb_message: Message | None, bot: Bot, db) -> None:
        chat_id = await db.get_setting(bot.id, "post_channel")
        title = "ulanmagan"
        if chat_id:
            try:
                title = (await bot.get_chat(int(chat_id))).title or chat_id
            except TelegramAPIError:
                title = f"{chat_id} (ma'lumot olinmadi)"
        await safe_edit(cb_message, f"📣 <b>Post kanali</b>\n\nHozirgi: <b>{esc(title)}</b>\n\n"
                                    "Yangi kino saqlanganda e'lon shu kanalga avtomatik joylanadi.",
                        postch_kb(bool(chat_id)))

    @router.callback_query(F.data == "adm:postch")
    async def cb_postch(cb: CallbackQuery, state: FSMContext, bot: Bot, db) -> None:
        await state.clear()
        await cb.answer()
        await _show_postch(cb.message, bot, db)

    @router.callback_query(F.data == "pc:set")
    async def cb_pc_set(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(ChannelStates.set_post)
        await cb.message.answer("🔗 Kanal <b>@username</b> yoki ID sini yuboring (yoki kanaldan post forward qiling).\n"
                                "⚠️ Bot kanalda <b>admin</b> bo'lib, xabar yuborish huquqiga ega bo'lishi kerak.")

    @router.message(ChannelStates.set_post)
    async def pc_got(message: Message, state: FSMContext, bot: Bot, db) -> None:
        try:
            chat = await resolve_chat(bot, message)
        except ValueError as e:
            await message.answer(f"❌ {esc(e)}\n\nQayta yuboring yoki /cancel.")
            return
        await db.set_setting(bot.id, "post_channel", str(chat.id))
        await state.clear()
        await message.answer(f"✅ Post kanali ulandi: <b>{esc(chat.title)}</b>", reply_markup=back_kb("adm:postch"))

    @router.callback_query(F.data == "pc:del")
    async def cb_pc_del(cb: CallbackQuery, bot: Bot, db) -> None:
        await db.del_setting(bot.id, "post_channel")
        await cb.answer("Uzildi")
        await _show_postch(cb.message, bot, db)

    # ---------------- Reklama / Broadcast ----------------
    @router.callback_query(F.data == "adm:bc")
    async def cb_bc(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(BroadcastStates.content)
        await cb.message.answer("📨 Reklama xabarini yuboring (matn, rasm, video, forward — istalgani).\n\n"
                                "Bekor qilish: /cancel")

    @router.message(BroadcastStates.content)
    async def bc_content(message: Message, state: FSMContext) -> None:
        await state.update_data(src_chat=message.chat.id, src_msg=message.message_id, buttons=[])
        await state.set_state(BroadcastStates.confirm)
        await message.answer("👆 Shu xabar yuboriladi. Davom etamizmi?", reply_markup=broadcast_kb())

    @router.callback_query(BroadcastStates.confirm, F.data == "bc:btn")
    async def bc_btn(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(BroadcastStates.button)
        await cb.message.answer("🔘 Tugmalarni har qatorga bittadan yuboring:\n<code>Matn - https://havola.uz</code>")

    @router.message(BroadcastStates.button, TEXT)
    async def bc_btn_got(message: Message, state: FSMContext) -> None:
        buttons: list[list[str]] = []
        for line in message.text.splitlines():
            m = re.match(r"^(.+?)\s*[-–|]\s*((?:https?|tg)://\S+)$", line.strip())
            if not m:
                await message.answer(f"⚠️ Noto'g'ri qator: <code>{esc(line)}</code>\nFormat: <code>Matn - https://...</code>")
                return
            buttons.append([m.group(1).strip(), m.group(2)])
        await state.update_data(buttons=buttons)
        await state.set_state(BroadcastStates.confirm)
        await message.answer(f"✅ {len(buttons)} ta tugma qo'shildi. Yuboramizmi?", reply_markup=broadcast_kb())

    @router.callback_query(BroadcastStates.confirm, F.data.in_({"bc:send", "bc:fwd"}))
    async def bc_send(cb: CallbackQuery, state: FSMContext, bot: Bot, db) -> None:
        data = await state.get_data()
        await state.clear()
        await cb.answer("🚀 Yuborish boshlandi")
        await safe_edit(cb.message, "🚀 Reklama yuborilmoqda... Tugagach hisobot keladi.")
        task = asyncio.create_task(_broadcast(
            bot, db, cb.message.chat.id, data["src_chat"], data["src_msg"],
            data.get("buttons", []), forward=(cb.data == "bc:fwd")))
        _background.add(task)
        task.add_done_callback(_background.discard)

    @router.callback_query(F.data == "bc:cancel")
    async def bc_cancel(cb: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await cb.answer("Bekor qilindi")
        await safe_edit(cb.message, "❌ Reklama bekor qilindi.", back_kb())

    # ---------------- Gemini API ----------------
    async def _show_gemini(cb_message: Message | None, bot: Bot, db) -> None:
        key = await db.get_setting(bot.id, "gemini_key", "")
        status = f"✅ Faol: <code>{esc(mask_key(key))}</code>" if key else "❌ Kalit kiritilmagan (AI o'chiq)"
        await safe_edit(cb_message, f"🤖 <b>Gemini AI</b>\n\n{status}\n\n"
                                    "Kalit bilan Kino AI va /logos bo'limlari ishlaydi.\n"
                                    "Kalit olish: aistudio.google.com/apikey", gemini_kb(bool(key)))

    @router.callback_query(F.data == "adm:gemini")
    async def cb_gemini(cb: CallbackQuery, state: FSMContext, bot: Bot, db) -> None:
        await state.clear()
        await cb.answer()
        await _show_gemini(cb.message, bot, db)

    @router.callback_query(F.data == "gm:set")
    async def cb_gm_set(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(SettingsStates.gemini_key)
        await cb.message.answer("🔑 Gemini <b>API kalitini</b> yuboring (xabar tekshirilgach o'chiriladi).\n\nBekor qilish: /cancel")

    @router.message(SettingsStates.gemini_key, TEXT)
    async def gm_got(message: Message, state: FSMContext, bot: Bot, db, gemini: GeminiService) -> None:
        key = message.text.strip()
        await try_delete(message)
        if not re.fullmatch(r"[A-Za-z0-9_\-]{20,80}", key):
            await message.answer("⚠️ Kalit formati noto'g'ri. Qayta yuboring yoki /cancel.")
            return
        status = await message.answer("⏳ Kalit tekshirilmoqda...")
        try:
            await gemini.generate(key, "Reply with the single word: OK", timeout=40)
        except GeminiError as e:
            await status.edit_text(f"❌ Kalit ishlamadi: {esc(e)}\n\nBoshqa kalit yuboring yoki /cancel.")
            return
        await db.set_setting(bot.id, "gemini_key", key)
        await state.clear()
        await status.edit_text("✅ Gemini API kaliti saqlandi. AI funksiyalari faollashdi!", reply_markup=back_kb("adm:gemini"))

    @router.callback_query(F.data == "gm:del")
    async def cb_gm_del(cb: CallbackQuery, bot: Bot, db) -> None:
        await db.del_setting(bot.id, "gemini_key")
        await cb.answer("O'chirildi")
        await _show_gemini(cb.message, bot, db)

    # ---------------- PIN boshqaruvi (faqat asosiy bot) ----------------
    if is_main:
        async def _show_pin(cb_message: Message | None, bot: Bot, db, config) -> None:
            enabled = await db.get_setting(bot.id, "pin_enabled", "1") == "1"
            custom = bool(await db.get_setting(bot.id, "pin_hash"))
            await safe_edit(
                cb_message,
                "🔐 <b>PIN boshqaruvi</b> (/shahriboi)\n\n"
                f"Holat: {'🔒 PIN so`raladi' if enabled else '🔓 PIN so`ralmaydi'}\n"
                f"PIN: {'o`zgartirilgan' if custom else 'standart (.env)'}",
                pin_kb(enabled))

        @router.callback_query(F.data == "adm:pin")
        async def cb_pin(cb: CallbackQuery, state: FSMContext, bot: Bot, db, config) -> None:
            await state.clear()
            await cb.answer()
            await _show_pin(cb.message, bot, db, config)

        @router.callback_query(F.data == "pin:toggle")
        async def cb_pin_toggle(cb: CallbackQuery, bot: Bot, db, config) -> None:
            enabled = await db.get_setting(bot.id, "pin_enabled", "1") == "1"
            await db.set_setting(bot.id, "pin_enabled", "0" if enabled else "1")
            await cb.answer("Yangilandi")
            await _show_pin(cb.message, bot, db, config)

        @router.callback_query(F.data == "pin:change")
        async def cb_pin_change(cb: CallbackQuery, state: FSMContext) -> None:
            await cb.answer()
            await state.set_state(SettingsStates.new_pin)
            await cb.message.answer("🔢 Yangi PIN-kodni yuboring (4–12 ta raqam).\n\nBekor qilish: /cancel")

        @router.message(SettingsStates.new_pin, TEXT)
        async def pin_got(message: Message, state: FSMContext, bot: Bot, db) -> None:
            pin = message.text.strip()
            await try_delete(message)
            if not re.fullmatch(r"\d{4,12}", pin):
                await message.answer("⚠️ PIN 4–12 ta raqamdan iborat bo'lishi kerak. Qayta yuboring yoki /cancel.")
                return
            await db.set_setting(bot.id, "pin_hash", hash_pin(pin))
            await db.set_setting(bot.id, "pin_enabled", "1")
            await state.clear()
            await message.answer("✅ Yangi PIN-kod saqlandi.", reply_markup=back_kb("adm:pin"))

    return router
