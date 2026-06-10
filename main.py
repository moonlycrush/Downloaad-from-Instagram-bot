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
# optional debug router (will log all incoming messages)
from handlers.debug import debug_router

# Default download dir (can be overridden via env var)
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "data/downloads")

# Logging level can be controlled via LOG_LEVEL env var. Use DEBUG for troubleshooting.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("🚀 Starting bot...")
    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)

    # Read token from environment
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise RuntimeError(
            "❌ BOT_TOKEN not set. Create a .env file or export BOT_TOKEN environment variable."
        )

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
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

    # include debug router last (it only logs incoming messages)
    # Enable it by setting LOG_LEVEL=DEBUG or DEBUG_RESPOND=1 to get replies
    dp.include_router(debug_router)

    logger.info("🎯 All routers loaded")
    logger.info("⏳ Bot is running... (Ctrl+C to stop)")

    try:
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Bot stopped")
    except Exception:
        logger.exception("❌ Unhandled exception in main")
