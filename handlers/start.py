"""handlers/start.py — Стартовое меню и помощь"""
import logging
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from keyboards.buttons import main_menu_kb
from keyboards.inline import help_kb

logger = logging.getLogger(__name__)
start_router = Router()

WELCOME_TEXT = (
    "👋 <b>Добро пожаловать в Media Downloader!</b>\n\n"
    "🤖 Я помогу вам скачать медиафайлы из:\n"
    "  • 📸 <b>Instagram</b> — фото, Reels, карусели\n"
    "  • ▶️ <b>YouTube</b> — видео, Shorts, MP3 аудио\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📌 <b>Как пользоваться:</b>\n"
    "Просто отправьте ссылку — бот сам всё определит!\n\n"
    "💡 Используйте кнопки меню ниже 👇"
)

HELP_TEXT = (
    "📚 <b>Справка по использованию бота</b>\n\n"
    "Выберите раздел для подробной информации:"
)

HELP_INSTAGRAM = (
    "📸 <b>Instagram — Инструкция</b>\n\n"
    "Отправьте ссылку на:\n"
    "  • <b>Пост</b> — <code>instagram.com/p/...</code>\n"
    "  • <b>Reels</b> — <code>instagram.com/reel/...</code>\n"
    "  • <b>IGTV</b> — <code>instagram.com/tv/...</code>\n\n"
    "После этого выберите, что скачать:\n"
    "  📥 Всё • 🖼 Только фото • 🎬 Только видео\n\n"
    "⚠️ Приватные аккаунты не поддерживаются."
)

HELP_YOUTUBE = (
    "▶️ <b>YouTube — Инструкция</b>\n\n"
    "Отправьте ссылку на:\n"
    "  • <b>Видео</b> — <code>youtube.com/watch?v=...</code>\n"
    "  • <b>Shorts</b> — <code>youtube.com/shorts/...</code>\n"
    "  • <b>Краткая</b> — <code>youtu.be/...</code>\n\n"
    "Затем выберите формат:\n"
    "  🎵 <b>MP3</b> — только аудио (192 kbps)\n"
    "  🎬 <b>Видео</b> — выбор качества: 360p / 480p / 720p / 1080p / Лучшее"
)

HELP_ABOUT = (
    "🤖 <b>О боте</b>\n\n"
    "Версия: <b>2.0</b>\n"
    "Движок: <b>aiogram 3 + yt-dlp + instaloader</b>\n\n"
    "📥 Поддерживаемые платформы:\n"
    "  • Instagram (фото, видео, Reels)\n"
    "  • YouTube (видео, Shorts, MP3)\n\n"
    "⚡ Бот скачивает файлы напрямую на сервер\n"
    "и отправляет вам через Telegram."
)


@start_router.message(Command("start"))
async def cmd_start(message: Message):
    # Сохраняем пользователя в БД
    try:
        db = getattr(message.bot, "db", None)
        if db:
            await db.upsert_user(
                user_id=message.from_user.id,
                username=message.from_user.username or "",
                first_name=message.from_user.first_name or "",
                join_date=datetime.utcnow().isoformat(),
                last_activity=datetime.utcnow().isoformat(),
            )
    except Exception:
        logger.exception("DB upsert error in /start")

    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@start_router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=help_kb())


# Обработка кнопки "ℹ️ Помощь" из reply-меню
@start_router.message(lambda m: m.text == "ℹ️ Помощь")
async def btn_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=help_kb())


# Обработка кнопки "📥 Скачать видео" — подсказка
@start_router.message(lambda m: m.text == "📥 Скачать видео")
async def btn_download(message: Message):
    await message.answer(
        "🔗 <b>Отправьте ссылку</b> на видео или пост:\n\n"
        "📸 <code>https://instagram.com/reel/...</code>\n"
        "▶️ <code>https://youtube.com/watch?v=...</code>\n"
        "🎯 <code>https://youtu.be/...</code>",
    )


# Обработка кнопки "👤 Профиль"
@start_router.message(lambda m: m.text == "👤 Профиль")
async def btn_profile(message: Message):
    db = getattr(message.bot, "db", None)
    user = message.from_user
    if db:
        try:
            stats = await db.get_user_stats(user.id)
            total     = stats.get("download_count", 0)
            insta     = stats.get("instagram_downloads", 0)
            youtube   = stats.get("youtube_downloads", 0)
        except Exception:
            total = insta = youtube = 0
    else:
        total = insta = youtube = 0

    name = user.full_name or user.username or "Пользователь"
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📛 Имя: {name}\n"
        f"🔗 Username: @{user.username or '—'}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Статистика скачиваний:</b>\n"
        f"  📥 Всего: <b>{total}</b>\n"
        f"  📸 Instagram: <b>{insta}</b>\n"
        f"  ▶️ YouTube: <b>{youtube}</b>"
    )
    await message.answer(text)


# Обработка кнопки "📊 Статистика"
@start_router.message(lambda m: m.text == "📊 Статистика")
async def btn_stats(message: Message):
    db = getattr(message.bot, "db", None)
    if not db:
        await message.answer("❌ База данных недоступна.")
        return
    try:
        stats = await db.get_stats()
        text = (
            "📊 <b>Общая статистика бота</b>\n\n"
            f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
            f"📸 Instagram загрузок: <b>{stats['instagram_downloads']}</b>\n"
            f"▶️ YouTube загрузок: <b>{stats['youtube_downloads']}</b>"
        )
        await message.answer(text)
    except Exception:
        await message.answer("❌ Ошибка получения статистики.")


# ─── Callback для кнопок помощи ───────────────────────────────────────────────
@start_router.callback_query(lambda c: c.data and c.data.startswith("help|"))
async def help_callback(query: CallbackQuery):
    await query.answer()
    section = query.data.split("|")[1]
    if section == "instagram":
        await query.message.edit_text(HELP_INSTAGRAM, reply_markup=help_kb())
    elif section == "youtube":
        await query.message.edit_text(HELP_YOUTUBE, reply_markup=help_kb())
    elif section == "about":
        await query.message.edit_text(HELP_ABOUT, reply_markup=help_kb())


# ─── Отмена любого действия ───────────────────────────────────────────────────
@start_router.callback_query(lambda c: c.data == "cancel")
async def cancel_callback(query: CallbackQuery):
    await query.answer("Отменено")
    await query.message.edit_text("❌ <b>Действие отменено.</b>\n\nОтправьте новую ссылку.")