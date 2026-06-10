"""handlers/youtube.py — Скачивание видео/аудио с YouTube"""
import asyncio
import logging
import re

from aiogram import Router
from aiogram.types import Message, CallbackQuery, FSInputFile

from keyboards.inline import youtube_choice_kb, youtube_quality_kb, store_url, get_url
from services.youtube_downloader import download_youtube

logger = logging.getLogger(__name__)
youtube_router = Router()

# Поддерживаемые форматы YouTube URL: watch, shorts, embed, youtu.be
YOUTUBE_RE = re.compile(
    r"(https?://(?:www\.)?(?:"
    r"youtube\.com/(?:watch\?v=|shorts/|embed/)|"
    r"youtu\.be/"
    r")[\w\-]+"
    r"(?:[?&][\w=&%\-]*)?)"
)


@youtube_router.message()
async def detect_youtube(message: Message):
    text = message.text or ""
    match = YOUTUBE_RE.search(text)
    if not match:
        return

    url = match.group(1)
    uid = store_url(url)
    kb  = youtube_choice_kb(uid)

    from aiogram.types import LinkPreviewOptions

    # Zero-width joiner hack to hide the URL text, making only the media preview visible
    invisible_link = f'<a href="{url}">&#8205;</a>'
    
    await message.reply(
        text=invisible_link,
        reply_markup=kb,
        link_preview_options=LinkPreviewOptions(
            url=url,
            is_disabled=False,
            prefer_large_media=True,
            show_above_text=True
        ),
        parse_mode="HTML"
    )


@youtube_router.callback_query(lambda c: c.data and c.data.startswith("yt|"))
async def youtube_callback(query: CallbackQuery):
    await query.answer()
    parts = query.data.split("|")

    if len(parts) < 3:
        await query.message.reply("❌ Неверный запрос.")
        return

    action = parts[1]
    uid    = parts[2]

    url = get_url(uid)
    if not url:
        await query.message.edit_text(
            "❌ <b>Ссылка устарела.</b>\n\nПожалуйста, отправьте ссылку заново."
        )
        return

    bot          = query.message.bot
    db           = getattr(bot, "db", None)
    download_dir = getattr(bot, "download_dir", "data/downloads")
    loop         = asyncio.get_running_loop()

    # ── Кнопка "Назад" ────────────────────────────────────────────────────────
    if action == "back":
        kb = youtube_choice_kb(uid)
        await query.message.edit_text(
            "▶️ <b>Выберите формат загрузки</b> 👇",
            reply_markup=kb,
        )
        return

    # ── Скачать аудио (MP3) ───────────────────────────────────────────────────
    if action == "audio":
        msg = await query.message.edit_text(
            "🎵 <b>Конвертирую в MP3...</b>\n\n"
            "⏳ Пожалуйста, подождите..."
        )
        try:
            out_path = await download_youtube(
                url, download_dir, loop,
                kind="audio", status_message=msg,
            )
            await query.message.reply_audio(
                FSInputFile(out_path),
                caption=(
                    "🎵 <b>Аудио готово!</b>\n\n"
                    "Качество: <b>192 kbps MP3</b>\n"
                    "Отправьте новую ссылку для следующей загрузки 🔗"
                ),
            )
            if db:
                await db.increment_download(query.from_user.id, kind="youtube")
            await msg.edit_text("✅ <b>Аудио успешно отправлено!</b>")
        except Exception:
            logger.exception("YouTube audio download error")
            await msg.edit_text(
                "❌ <b>Ошибка загрузки аудио.</b>\n\n"
                "Попробуйте ещё раз или проверьте ссылку."
            )
        return

    # ── Выбор качества видео ──────────────────────────────────────────────────
    if action == "video":
        kb = youtube_quality_kb(uid)
        await query.message.edit_text(
            "🎬 <b>Выберите качество видео</b> 👇\n\n"
            "📱 360p — лёгкий файл\n"
            "📺 480p — стандартное\n"
            "🖥 720p — HD\n"
            "🖥 1080p — Full HD\n"
            "⭐ Лучшее — максимальное доступное",
            reply_markup=kb,
        )
        return

    # ── Скачать видео в выбранном качестве ───────────────────────────────────
    if action == "quality":
        if len(parts) < 4:
            await query.message.reply("❌ Качество не указано.")
            return

        quality = parts[3]
        labels  = {
            "360p": "360p 📱",
            "480p": "480p 📺",
            "720p": "720p HD 🖥",
            "1080p": "1080p FHD 🖥",
            "best": "Лучшее ⭐",
        }
        label = labels.get(quality, quality)

        msg = await query.message.edit_text(
            f"⬇️ <b>Загружаю видео {label}</b>\n\n"
            "Пожалуйста, подождите — это может занять некоторое время..."
        )
        try:
            out_path = await download_youtube(
                url, download_dir, loop,
                kind="video", quality=quality, status_message=msg,
            )
            await query.message.reply_video(
                FSInputFile(out_path),
                caption=(
                    f"🎬 <b>Видео готово! ({label})</b>\n\n"
                    "Отправьте новую ссылку для следующей загрузки 🔗"
                ),
                supports_streaming=True,
            )
            if db:
                await db.increment_download(query.from_user.id, kind="youtube")
            await msg.edit_text(f"✅ <b>Видео {label} успешно отправлено!</b>")
        except Exception:
            logger.exception("YouTube video download error")
            await msg.edit_text(
                "❌ <b>Ошибка загрузки видео.</b>\n\n"
                "Попробуйте другое качество или проверьте ссылку."
            )
        return