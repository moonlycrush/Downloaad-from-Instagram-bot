"""handlers/instagram.py — Скачивание медиа из Instagram"""
import logging
import re

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
        await query.message.reply("❌ Неверный запрос.")
        return

    mode = parts[1]   # all | photo | video
    uid  = parts[2]

    url = get_url(uid)
    if not url:
        await query.message.edit_text(
            "❌ <b>Ссылка устарела.</b>\n\nПожалуйста, отправьте ссылку заново."
        )
        return

    bot          = query.message.bot
    db           = getattr(bot, "db", None)
    download_dir = getattr(bot, "download_dir", "data/downloads")

    mode_label = {"all": "Всё", "photo": "Только фото", "video": "Только видео"}.get(mode, "Всё")
    msg = await query.message.edit_text(
        f"⏳ <b>Загружаю:</b> {mode_label}...\n\n"
        "Пожалуйста, подождите — это может занять несколько секунд."
    )

    try:
        files = await download_instagram(url, download_dir)
        if not files:
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

        # Фильтр по режиму
        if mode == "photo":
            videos = []
        elif mode == "video":
            photos = []

        if not photos and not videos:
            await msg.edit_text("❌ Файлы выбранного типа не найдены.")
            return

        await msg.edit_text("✅ <b>Загружено! Отправляю файлы...</b>")

        # ── Отправка фото группой ─────────────────────────────────────────────
        if photos:
            media_group = [InputMediaPhoto(media=FSInputFile(p)) for p in photos[:10]]
            try:
                await query.message.reply_media_group(media_group)
            except Exception:
                for p in photos[:10]:
                    try:
                        await query.message.reply_photo(FSInputFile(p))
                    except Exception:
                        logger.exception("Ошибка отправки фото: %s", p)

        # ── Отправка видео ──────────────────────────────────────────────────
        for v in videos[:5]:
            try:
                await query.message.reply_video(
                    FSInputFile(v),
                    caption="🎬 <b>Instagram видео</b>",
                    supports_streaming=True,
                )
            except Exception:
                try:
                    await query.message.reply_document(
                        FSInputFile(v),
                        caption="🎬 Instagram видео (файл)",
                    )
                except Exception:
                    logger.exception("Ошибка отправки видео: %s", v)

        # Обновляем статистику
        if db:
            await db.increment_download(query.from_user.id, kind="instagram")

        total = len(photos) + len(videos)
        await query.message.reply(
            f"✅ <b>Готово!</b> Отправлено <b>{total}</b> файл(ов).\n\n"
            "Отправьте новую ссылку для следующей загрузки 🔗"
        )

    except Exception:
        logger.exception("Instagram callback error")
        await msg.edit_text(
            "❌ <b>Ошибка при загрузке.</b>\n\n"
            "Попробуйте позже или проверьте ссылку."
        )
