"""Yordamchi funksiyalar."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import Chat, InlineKeyboardMarkup, Message, MessageOriginChannel

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=5))  # O'zbekiston vaqti


def now_str() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def today_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


# ---------------- PIN xavfsizligi ----------------
def hash_pin(pin: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def check_pin_hash(pin: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(hash_pin(pin, salt).split("$", 1)[1], digest)


def mask_key(key: str) -> str:
    return key if len(key) <= 10 else f"{key[:6]}…{key[-4:]}"


# ---------------- Matn yordamchilari ----------------
def make_hashtags(raw: str) -> str:
    parts = [p for p in re.split(r"[,;\n]+", raw) if p.strip()]
    if len(parts) == 1 and " " in parts[0].strip():
        parts = parts[0].split()
    tags = []
    for p in parts:
        clean = re.sub(r"[^\w]", "", p.replace("#", ""), flags=re.UNICODE)
        if clean:
            tags.append("#" + clean)
    return " ".join(tags) if tags else "#kino"


def build_caption(m: dict, username: str) -> str:
    return (
        f"🎬 <b>{esc(m['title'])}</b>\n"
        f"📅 Yili: {esc(m['year'])}\n"
        f"🖥 Sifati: {esc(m['quality'])}\n"
        f"🗽 Davlati: {esc(m['country'])}\n"
        f"🇺🇿 Tili: {esc(m['language'])}\n"
        f"🍿 Janri: {esc(m['genre'])}\n\n"
        f"🤖 @{esc(username)}"
    )


def build_post_text(m: dict, username: str) -> str:
    return (
        f"🎬 <b>{esc(m['title'])}</b>\n"
        f"📅 Yili: {esc(m['year'])}\n"
        f"🖥 Sifati: {esc(m['quality'])}\n"
        f"🗽 Davlati: {esc(m['country'])}\n"
        f"🇺🇿 Tili: {esc(m['language'])}\n"
        f"🍿 Janri: {esc(m['genre'])}\n"
        f"✅ Filmni ko'rish uchun &lt;&lt; <b>{esc(m['code'])}</b> ⬆️ kodini @{esc(username)} ga yuboring 🍿"
    )


async def reply_long(message: Message, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None,
                     chunk: int = 3900) -> None:
    """Uzun (AI) javobni bo'laklab, HTML belgilarsiz yuboradi."""
    text = (text or "").strip() or "…"
    parts = [text[i:i + chunk] for i in range(0, len(text), chunk)]
    for i, part in enumerate(parts):
        await message.answer(part, parse_mode=None,
                             reply_markup=reply_markup if i == len(parts) - 1 else None)


async def safe_edit(message: Optional[Message], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> None:
    if message is None:
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "not modified" in str(e).lower():
            return
        await message.answer(text, reply_markup=reply_markup)
    except TelegramAPIError:
        logger.exception("safe_edit xatosi")


async def try_delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramAPIError:
        pass


# ---------------- Kanal / obuna ----------------
async def resolve_chat(bot: Bot, message: Message) -> Chat:
    """@username, ID yoki forward qilingan postdan kanalni aniqlaydi. Bot admin bo'lishi shart."""
    origin = message.forward_origin
    if isinstance(origin, MessageOriginChannel):
        ref: Any = origin.chat.id
    else:
        text = (message.text or "").strip()
        if not text:
            raise ValueError("Kanal @username, ID yuboring yoki kanaldan post forward qiling.")
        if re.fullmatch(r"-?\d+", text):
            ref = int(text)
        else:
            ref = text if text.startswith("@") else "@" + text.split("t.me/")[-1].strip("/@")
    try:
        chat = await bot.get_chat(ref)
    except TelegramAPIError:
        raise ValueError("Kanal topilmadi. Username/ID to'g'riligini tekshiring.")
    try:
        member = await bot.get_chat_member(chat.id, bot.id)
    except TelegramAPIError:
        raise ValueError("Botning kanaldagi huquqlarini aniqlab bo'lmadi.")
    if member.status != ChatMemberStatus.ADMINISTRATOR:
        raise ValueError("Bot bu kanalda admin emas. Avval botni kanalga ADMIN qiling.")
    return chat


async def get_chat_link(bot: Bot, chat: Chat) -> str:
    if chat.username:
        return f"https://t.me/{chat.username}"
    if chat.invite_link:
        return chat.invite_link
    try:
        return await bot.export_chat_invite_link(chat.id)
    except TelegramAPIError:
        raise ValueError("Havola olinmadi. Botga 'Havola yaratish' huquqini bering.")


async def is_admin(db, config, bot_id: int, user_id: int) -> bool:
    if user_id in config.admin_ids:
        return True
    row = await db.get_bot(bot_id)
    return bool(row and row["owner_id"] == user_id)


async def missing_channels(bot: Bot, db, user_id: int) -> list[dict]:
    missing = []
    for ch in await db.list_channels(bot.id):
        try:
            m = await bot.get_chat_member(ch["chat_id"], user_id)
        except TelegramAPIError:
            logger.warning("Obuna tekshirib bo'lmadi: %s", ch["chat_id"])
            continue
        if m.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
            missing.append(ch)
        elif m.status == ChatMemberStatus.RESTRICTED and not getattr(m, "is_member", True):
            missing.append(ch)
    return missing


# ---------------- SVG ----------------
_SVG_RE = re.compile(r"<svg\b[\s\S]*</svg>", re.IGNORECASE)


def extract_svg(raw: str) -> Optional[str]:
    m = _SVG_RE.search(raw or "")
    if not m:
        return None
    svg = m.group(0)
    svg = re.sub(r"<script\b[\s\S]*?</script>", "", svg, flags=re.I)
    svg = re.sub(r"<foreignObject\b[\s\S]*?</foreignObject>", "", svg, flags=re.I)
    svg = re.sub(r"<image\b[^>]*>", "", svg, flags=re.I)
    svg = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*')", "", svg, flags=re.I)
    svg = re.sub(r"(xlink:)?href\s*=\s*(\"(?!#)[^\"]*\"|'(?!#)[^']*')", "", svg, flags=re.I)
    if "xmlns=" not in svg[:400]:
        svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    return svg


async def svg_to_png(svg: str) -> Optional[bytes]:
    def _convert() -> Optional[bytes]:
        try:
            import cairosvg  # type: ignore
        except Exception:
            return None
        try:
            return cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=1024,
                                    output_height=1024, background_color="white")
        except Exception:
            logger.exception("SVG -> PNG xatosi")
            return None

    return await asyncio.to_thread(_convert)


# ---------------- Serial matnlari ----------------
def build_series_caption(s: dict, username: str, episodes: int) -> str:
    return (
        f"📺 <b>{esc(s['title'])}</b>\n"
        f"📅 Yili: {esc(s['year'])}\n"
        f"🖥 Sifati: {esc(s['quality'])}\n"
        f"🗽 Davlati: {esc(s['country'])}\n"
        f"🇺🇿 Tili: {esc(s['language'])}\n"
        f"🍿 Janri: {esc(s['genre'])}\n"
        f"🎞 Qismlar soni: {episodes}\n\n"
        f"👇 Ko'rish uchun qismni tanlang\n🤖 @{esc(username)}"
    )


def build_series_post_text(s: dict, username: str) -> str:
    return (
        f"📺 <b>{esc(s['title'])}</b> (serial)\n"
        f"📅 Yili: {esc(s['year'])}\n"
        f"🖥 Sifati: {esc(s['quality'])}\n"
        f"🗽 Davlati: {esc(s['country'])}\n"
        f"🇺🇿 Tili: {esc(s['language'])}\n"
        f"🍿 Janri: {esc(s['genre'])}\n"
        f"✅ Serialni ko'rish uchun &lt;&lt; <b>{esc(s['code'])}</b> ⬆️ kodini @{esc(username)} ga yuboring 🍿"
    )
