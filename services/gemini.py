"""Gemini AI xizmati (google-generativeai)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import google.generativeai as genai

logger = logging.getLogger(__name__)


class GeminiError(Exception):
    """Foydalanuvchiga ko'rsatish mumkin bo'lgan Gemini xatosi."""


class GeminiService:
    def __init__(self, default_key: str, model_name: str) -> None:
        self.default_key = default_key
        self.model_name = model_name
        # genai.configure global bo'lgani uchun turli kalitlar aralashib ketmasligi uchun lock
        self._lock = asyncio.Lock()

    async def resolve_key(self, db, bot_id: int) -> str:
        return (await db.get_setting(bot_id, "gemini_key", "")) or self.default_key or ""

    async def generate(self, api_key: str, contents: Any, system_instruction: Optional[str] = None,
                       temperature: float = 0.8, timeout: int = 90) -> str:
        if not api_key:
            raise GeminiError("Gemini API kaliti kiritilmagan.")
        async with self._lock:
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(self.model_name, system_instruction=system_instruction)
                response = await asyncio.wait_for(
                    model.generate_content_async(
                        contents, generation_config=genai.GenerationConfig(temperature=temperature)),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                raise GeminiError("Gemini javob bermadi (vaqt tugadi). Qayta urinib ko'ring.")
            except Exception as e:  # noqa: BLE001
                logger.warning("Gemini xatosi: %s", e)
                msg = str(e)
                if "API key" in msg or "API_KEY" in msg or "403" in msg or "400" in msg:
                    raise GeminiError("API kalit noto'g'ri yoki ruxsat yo'q.")
                if "429" in msg or "quota" in msg.lower():
                    raise GeminiError("Gemini limiti tugadi. Birozdan so'ng urinib ko'ring.")
                raise GeminiError("Gemini bilan bog'lanishda xatolik yuz berdi.")
        try:
            text = response.text
        except Exception:  # noqa: BLE001
            raise GeminiError("Gemini javobi bloklandi yoki bo'sh keldi.")
        if not text or not text.strip():
            raise GeminiError("Gemini bo'sh javob qaytardi.")
        return text
