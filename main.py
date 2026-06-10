"""main.py - Bot entrypoint"""
import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

# from config import BOT_TOKEN
from database import Database
from middlewares.registration import RegistrationMiddleware
from middlewares.rate_limit import RateLimitMiddleware

# Import routers directly from handler modules to avoid package shadowing issues
from handlers.start import start_router
from handlers.instagram import instagram_router
from handlers.youtube import youtube_router
from handlers.admin import admin_router

# Default download dir (can be overridden via env var)
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "data/downloads")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Starting bot...")
    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)

    bot = Bot(token="8601595538:AAHpbSDpDLmQYjVuCYfN66MlpGw-d6NyK5w", default=DefaultBotProperties(parse_mode="HTML"))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Initialize DB
    db = Database()
    await db.connect()
    await db.create_tables()

    # register middlewares
    dp.update.middleware.register(RegistrationMiddleware(db))
    dp.update.middleware.register(RateLimitMiddleware(max_per_second=1.0))

    # attach shared objects in dispatcher mapping
    dp["db"] = db
    dp["download_dir"] = DOWNLOAD_DIR
    dp["loop"] = asyncio.get_running_loop()

    # Also set attributes on bot for convenience in handlers: message.bot.db etc.
    bot.db = db
    bot.download_dir = DOWNLOAD_DIR
    bot.loop = asyncio.get_running_loop()

    # include routers
    dp.include_router(start_router)
    dp.include_router(instagram_router)
    dp.include_router(youtube_router)
    dp.include_router(admin_router)

    try:
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")