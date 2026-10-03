# Kodli Kino Bot (aiogram 3.x)

## Ishga tushirish
1. `pip install -r requirements.txt`
2. `.env.example` ni `.env` ga nusxalang va to'ldiring (BOT_TOKEN, ADMIN_IDS).
3. `python main.py`

## Foydalanish
- Asosiy botda `/shahriboi` → PIN (standart 9767) → BotFather tokeni → yangi Kino Bot fonda ishga tushadi.
- Yangi bot egasi o'z botida `/admin` orqali kino qo'shadi, kanal ulaydi, Gemini kalitini kiritadi.
- `/admin` → 🤖 Gemini API: kalit kiritilishi bilan Kino AI va `/logos` ishlaydi.
- `/logos`: logotip yasash (SVG, PNG) va dizayn bo'yicha savol-javob.

## Eslatmalar
- Har bir bot (asosiy va child) ma'lumotlari `bot_id` bo'yicha alohida saqlanadi.
- Kino post kanali (📣) va majburiy obuna kanallarida bot ADMIN bo'lishi shart.
- Child bot tokenlari SQLite faylida saqlanadi — `data/kino.db` ni himoya qiling.
