"""Kodli Kino Bot — ishga tushirish nuqtasi."""
from __future__ import annotations

import asyncio
import logging

from config import load_config
from database import Database
from services.bot_manager import BotManager
from services.gemini import GeminiService


async def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    config = load_config()
    db = Database(config.db_path)
    await db.init()
    gemini = GeminiService(config.gemini_api_key, config.gemini_model)
    manager = BotManager(db, config, gemini)

    main_task = await manager.start_main()
    await manager.start_saved_children()
    try:
        await main_task
    finally:
        await manager.shutdown()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("To'xtatildi.")
