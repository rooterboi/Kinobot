"""Klaviaturalar."""
from __future__ import annotations

from typing import Optional

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

BTN_AI = "🤖 Kino AI"
BTN_LOGO = "🎨 Logotip (/logos)"
BTN_EXIT = "❌ Chiqish"


def user_menu_kb() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text=BTN_AI)
    b.button(text=BTN_LOGO)
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)


def exit_kb() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text=BTN_EXIT)
    return b.as_markup(resize_keyboard=True)


def open_bot_kb(username: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎬 Botga o'tish", url=f"https://t.me/{username}")
    return b.as_markup()


def subscribe_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.button(text=f"📢 {ch['title'] or 'Kanal'}", url=ch["link"])
    b.button(text="✅ Tekshirish", callback_data="check_sub")
    b.adjust(1)
    return b.as_markup()


def admin_menu_kb(is_main: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📊 Statistika", callback_data="adm:stats")
    b.button(text="🎬 Kinolar", callback_data="adm:movies")
    b.button(text="📺 Seriallar", callback_data="adm:series")
    b.button(text="📢 Majburiy obuna", callback_data="adm:channels")
    b.button(text="📣 Post kanali", callback_data="adm:postch")
    b.button(text="📨 Reklama yuborish", callback_data="adm:bc")
    b.button(text="🤖 Gemini API", callback_data="adm:gemini")
    if is_main:
        b.button(text="🔐 PIN boshqaruvi", callback_data="adm:pin")
    b.button(text="❌ Yopish", callback_data="adm:close")
    b.adjust(2)
    return b.as_markup()


def back_kb(target: str = "adm:menu") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Orqaga", callback_data=target)
    return b.as_markup()


def movies_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Kino qo'shish", callback_data="mov:add")
    b.button(text="✏️ Tahrirlash", callback_data="mov:edit")
    b.button(text="🗑 Kodi bo'yicha o'chirish", callback_data="mov:del")
    b.button(text="📋 Ro'yxat", callback_data="mov:list")
    b.button(text="⬅️ Orqaga", callback_data="adm:menu")
    b.adjust(2, 1, 1, 1)
    return b.as_markup()


def edit_fields_kb(prefix: str = "mov:ef") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, label in (("title", "🎬 Nomi"), ("year", "📅 Yili"), ("quality", "🖥 Sifati"),
                       ("country", "🗽 Davlati"), ("language", "🇺🇿 Tili"),
                       ("genre", "🍿 Janri"), ("code", "🔢 Kodi")):
        b.button(text=label, callback_data=f"{prefix}:{key}")
    b.adjust(2)
    return b.as_markup()


def confirm_delete_kb(code: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha, o'chirish", callback_data=f"mov:delok:{code}")
    b.button(text="❌ Bekor qilish", callback_data="adm:movies")
    b.adjust(2)
    return b.as_markup()


def channels_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.button(text=f"🗑 {ch['title'] or ch['chat_id']}", callback_data=f"ch:del:{ch['id']}")
    b.button(text="➕ Kanal qo'shish", callback_data="ch:add")
    b.button(text="⬅️ Orqaga", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def postch_kb(has_channel: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔗 Kanalni ulash / almashtirish", callback_data="pc:set")
    if has_channel:
        b.button(text="🗑 Uzish", callback_data="pc:del")
    b.button(text="⬅️ Orqaga", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def broadcast_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Yuborish", callback_data="bc:send")
    b.button(text="↪️ Forward qilib yuborish", callback_data="bc:fwd")
    b.button(text="🔘 Inline tugma qo'shish", callback_data="bc:btn")
    b.button(text="❌ Bekor qilish", callback_data="bc:cancel")
    b.adjust(1)
    return b.as_markup()


def gemini_kb(has_key: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔑 Kalitni kiritish / yangilash", callback_data="gm:set")
    if has_key:
        b.button(text="🗑 Kalitni o'chirish", callback_data="gm:del")
    b.button(text="⬅️ Orqaga", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def pin_kb(enabled: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔢 PIN-kodni o'zgartirish", callback_data="pin:change")
    b.button(text="🔓 PIN so'rashni o'chirish" if enabled else "🔒 PIN so'rashni yoqish",
             callback_data="pin:toggle")
    b.button(text="⬅️ Orqaga", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def logos_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎨 Logotip yasash", callback_data="logo:make")
    b.button(text="❓ Savol-javob", callback_data="logo:qa")
    b.button(text="❌ Yopish", callback_data="logo:close")
    b.adjust(1)
    return b.as_markup()


def logo_result_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Qayta yasash", callback_data="logo:redo")
    b.button(text="✏️ O'zgartirish", callback_data="logo:edit")
    b.button(text="🏠 Menyu", callback_data="logo:menu")
    b.adjust(2, 1)
    return b.as_markup()


def logo_nav_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🏠 Menyu", callback_data="logo:menu")
    return b.as_markup()


def retry_logo_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Qayta urinish", callback_data="logo:redo")
    b.button(text="🏠 Menyu", callback_data="logo:menu")
    b.adjust(2)
    return b.as_markup()


# ---------------- Seriallar ----------------
EP_PAGE = 20


def series_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Serial qo'shish", callback_data="ser:add")
    b.button(text="➕ Qism qo'shish", callback_data="ser:ep")
    b.button(text="✏️ Tahrirlash", callback_data="ser:edit")
    b.button(text="🗑 Serialni o'chirish", callback_data="ser:del")
    b.button(text="🗑 Qismni o'chirish", callback_data="ser:epdel")
    b.button(text="📋 Ro'yxat", callback_data="ser:list")
    b.button(text="⬅️ Orqaga", callback_data="adm:menu")
    b.adjust(2, 1, 2, 1, 1)
    return b.as_markup()


def confirm_series_delete_kb(code: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha, o'chirish", callback_data=f"ser:delok:{code}")
    b.button(text="❌ Bekor qilish", callback_data="adm:series")
    b.adjust(2)
    return b.as_markup()


def episodes_done_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tugatish", callback_data="ser:epdone")
    return b.as_markup()


def episodes_kb(series_id: int, numbers: list[int], page: int = 0) -> InlineKeyboardMarkup:
    """Qismlar tugmalari (sahifalangan, 5 tadan qatorda)."""
    pages = max(1, (len(numbers) + EP_PAGE - 1) // EP_PAGE)
    page = min(max(page, 0), pages - 1)
    chunk = numbers[page * EP_PAGE:(page + 1) * EP_PAGE]
    b = InlineKeyboardBuilder()
    for n in chunk:
        b.button(text=str(n), callback_data=f"ep:{series_id}:{n}")
    b.adjust(5)
    if pages > 1:
        nav = InlineKeyboardBuilder()
        if page > 0:
            nav.button(text="⬅️", callback_data=f"epl:{series_id}:{page - 1}")
        nav.button(text=f"{page + 1}/{pages}", callback_data="noop")
        if page < pages - 1:
            nav.button(text="➡️", callback_data=f"epl:{series_id}:{page + 1}")
        nav.adjust(3)
        b.attach(nav)
    return b.as_markup()


def episode_nav_kb(series_id: int, number: int, numbers: list[int]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    idx = numbers.index(number) if number in numbers else -1
    row = 0
    if idx > 0:
        b.button(text=f"⬅️ {numbers[idx - 1]}-qism", callback_data=f"ep:{series_id}:{numbers[idx - 1]}")
        row += 1
    if 0 <= idx < len(numbers) - 1:
        b.button(text=f"{numbers[idx + 1]}-qism ➡️", callback_data=f"ep:{series_id}:{numbers[idx + 1]}")
        row += 1
    b.button(text="📋 Barcha qismlar", callback_data=f"epm:{series_id}")
    b.adjust(*(([row] if row else []) + [1]))
    return b.as_markup()
