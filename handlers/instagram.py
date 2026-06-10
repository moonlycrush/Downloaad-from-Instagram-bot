"""handlers/instagram.py — Скачивание медиа из Instagram"""
import logging
import re
import os

from aiogram import Router
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InputMediaVideo, FSInputFile

from keyboards.inline import instagram_choice_kb, store_url, get_url
from services.instagram_downloader import download_instagram

logger = logging.getLogger(__name__)
instagram_router = Router()

# Поддерживаемые форматы Instagram URL
INSTAGRAM_URL_RE = re.compile(
    r"(https?://(?:www\.)?instagram\.com/"
    r"(?:p|reel|tv|stories)/[^\s/?#]+"
    r"(?:/[^\s]*)?"
    r")"
)


@instagram_router.message()
async def detect_instagram(message: Message):
    text = message.text or ""
    match = INSTAGRAM_URL_RE.search(text)
    if not match:
        return

    # Очищаем URL от query-параметров
    url = match.group(1).split("?")[0].rstrip("/")
    uid = store_url(url)
    kb  = instagram_choice_kb(uid)

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


@instagram_router.callback_query(lambda c: c.data and c.data.startswith("ig|"))
async def instagram_callback(query: CallbackQuery):
    await query.answer()
    parts = query.data.split("|")

    if len(parts) < 3:
        logger.error("❌ Instagram callback: Invalid data format - %s", query.data)
        await query.message.reply("❌ Неверный запрос.")
        return

    mode = parts[1]   # all | photo | video
    uid  = parts[2]

    url = get_url(uid)
    if not url:
        logger.warning("⚠️ Instagram callback: URL expired or not found for uid=%s", uid)
        await query.message.edit_text(
            "❌ <b>Ссылка устарела.</b>\n\nПожалуйста, отправьте ссылку заново."
        )
        return

    bot          = query.message.bot
    db           = getattr(bot, "db", None)
    download_dir = getattr(bot, "download_dir", "data/downloads")
    user_id      = query.from_user.id

    logger.info("📥 Instagram callback started - URL: %s | Mode: %s | User: %s", url, mode, user_id)

    mode_label = {"all": "Всё", "photo": "Только фото", "video": "Только видео"}.get(mode, "Всё")
    msg = await query.message.edit_text(
        f"⏳ <b>Загружаю:</b> {mode_label}...\n\n"
        "Пожалуйста, подождите — это может занять несколько секунд."
    )

    try:
        logger.info("🔄 Starting download from Instagram - URL: %s | User: %s", url, user_id)
        files = await download_instagram(url, download_dir)
        logger.info("✅ Download completed - Files: %d | User: %s", len(files) if files else 0, user_id)
        
        if not files:
            logger.warning("⚠️ Instagram: No files downloaded - URL: %s | User: %s", url, user_id)
            await msg.edit_text(
                "❌ <b>Файлы не найдены.</b>\n\n"
                "Возможные причины:\n"
                "  • Приватный аккаунт\n"
                "  • Удалённый пост\n"
                "  • Неверная ссылка"
            )
            return

        # Разделяем по типу
        photos = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
        videos = [f for f in files if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv"))]

        logger.info("📊 Files categorized - Photos: %d | Videos: %d | User: %s", 
                   len(photos), len(videos), user_id)

        # Фильтр по режиму
        if mode == "photo":
            videos = []
            logger.info("🎨 Mode: PHOTO ONLY | User: %s", user_id)
        elif mode == "video":
            photos = []
            logger.info("🎬 Mode: VIDEO ONLY | User: %s", user_id)
        else:
            logger.info("🎨🎬 Mode: ALL (photos + videos) | User: %s", user_id)

        if not photos and not videos:
            logger.warning("⚠️ Instagram: No files match selected mode - Mode: %s | User: %s", mode, user_id)
            await msg.edit_text("❌ Файлы выбранного типа не найдены.")
            return

        await msg.edit_text("✅ <b>Загружено! Отправляю файлы...</b>")

        # ── Отправка фото группой ─────────────────────────────────────────────
        sent_photos = 0
        sent_videos = 0
        failed_files = []

        if photos:
            logger.info("📤 Starting photo upload - Count: %d | User: %s", len(photos[:10]), user_id)
            media_group = [InputMediaPhoto(media=FSInputFile(p)) for p in photos[:10]]
            try:
                await query.message.reply_media_group(media_group)
                sent_photos = len(photos[:10])
                logger.info("✅ Photos uploaded successfully - Count: %d | User: %s", sent_photos, user_id)
            except Exception as e:
                logger.error("❌ Failed to upload photos as media_group - Error: %s | User: %s", 
                           str(e), user_id)
                # Попытка отправить фото по одному
                logger.info("🔄 Attempting to upload photos individually...")
                for idx, p in enumerate(photos[:10], 1):
                    try:
                        logger.debug("📤 Uploading photo %d/%d - File: %s", idx, len(photos[:10]), p)
                        await query.message.reply_photo(FSInputFile(p))
                        sent_photos += 1
                        logger.info("✅ Photo %d uploaded - User: %s", idx, user_id)
                    except Exception as photo_error:
                        logger.error("❌ Failed to upload photo %d - File: %s | Error: %s | User: %s", 
                                   idx, os.path.basename(p), str(photo_error), user_id)
                        failed_files.append(os.path.basename(p))

        # ── Отправка видео ──────────────────────────────────────────────────
        if videos:
            logger.info("📤 Starting video upload - Count: %d | User: %s", len(videos[:5]), user_id)
            for idx, v in enumerate(videos[:5], 1):
                try:
                    file_size_mb = os.path.getsize(v) / (1024 * 1024)
                    logger.debug("📤 Uploading video %d/%d - File: %s | Size: %.2f MB", 
                               idx, len(videos[:5]), os.path.basename(v), file_size_mb)
                    
                    if file_size_mb > 50:
                        logger.warning("⚠️ Video file too large - File: %s | Size: %.2f MB | Trying as document...", 
                                     os.path.basename(v), file_size_mb)
                        await query.message.reply_document(
                            FSInputFile(v),
                            caption=f"🎬 Instagram видео (файл - {file_size_mb:.1f} MB)",
                        )
                    else:
                        await query.message.reply_video(
                            FSInputFile(v),
                            caption="🎬 <b>Instagram видео</b>",
                            supports_streaming=True,
                        )
                    
                    sent_videos += 1
                    logger.info("✅ Video %d uploaded - File: %s | User: %s", 
                              idx, os.path.basename(v), user_id)
                except Exception as video_error:
                    logger.error("❌ Failed to upload video %d - File: %s | Error: %s | Type: %s | User: %s", 
                               idx, os.path.basename(v), str(video_error), type(video_error).__name__, user_id)
                    try:
                        logger.info("🔄 Attempting to upload video as document...")
                        await query.message.reply_document(
                            FSInputFile(v),
                            caption="🎬 Instagram видео (файл)",
                        )
                        sent_videos += 1
                        logger.info("✅ Video uploaded as document - User: %s", user_id)
                    except Exception as doc_error:
                        logger.error("❌ Failed to upload video as document - File: %s | Error: %s | User: %s", 
                                   os.path.basename(v), str(doc_error), user_id)
                        failed_files.append(os.path.basename(v))

        # Обновляем статистику
        if db:
            try:
                await db.increment_download(query.from_user.id, kind="instagram")
                logger.info("✅ Database updated - User: %s", user_id)
            except Exception as db_error:
                logger.error("⚠️ Failed to update database - Error: %s | User: %s", str(db_error), user_id)

        total_sent = sent_photos + sent_videos
        logger.info("📊 Upload summary - Photos sent: %d | Videos sent: %d | Failed: %d | User: %s", 
                   sent_photos, sent_videos, len(failed_files), user_id)

        if failed_files:
            summary_text = (
                f"✅ <b>Готово!</b> Отправлено <b>{total_sent}</b> файл(ов).\n\n"
                f"⚠️ Не удалось отправить: {', '.join(failed_files[:3])}\n\n"
                "Отправьте новую ссылку для следующей загрузки 🔗"
            )
            logger.warning("⚠️ Some files failed to upload - Failed: %s | User: %s", 
                         str(failed_files), user_id)
        else:
            summary_text = (
                f"✅ <b>Готово!</b> Отправлено <b>{total_sent}</b> файл(ов).\n\n"
                "Отправьте новую ссылку для следующей загрузки 🔗"
            )

        await query.message.reply(summary_text)
        logger.info("✅ Instagram callback completed successfully - User: %s", user_id)

    except Exception as main_error:
        logger.error("❌ CRITICAL ERROR in Instagram callback - Error: %s | Type: %s | User: %s | URL: %s", 
                   str(main_error), type(main_error).__name__, user_id, url, exc_info=True)
        try:
            await msg.edit_text(
                "❌ <b>Ошибка при загрузке.</b>\n\n"
                "Попробуйте позже или проверьте ссылку."
            )
        except Exception as edit_error:
            logger.error("❌ Failed to edit error message - Error: %s | User: %s", 
                       str(edit_error), user_id)
