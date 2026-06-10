"""keyboards/inline.py

ВАЖНО: Telegram callback_data лимит — 64 байта.
URL хранится в кеше, в callback_data передаётся только короткий uid (8 символов).
"""
import uuid
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Глобальный URL-кеш: uid -> url
_url_store: dict[str, str] = {}


def store_url(url: str) -> str:
    """Сохраняет URL в кеш и возвращает короткий uid."""
    uid = uuid.uuid4().hex[:8]
    _url_store[uid] = url
    return uid


def get_url(uid: str) -> str | None:
    """Возвращает URL по uid из кеша."""
    return _url_store.get(uid)


# ─── YouTube ──────────────────────────────────────────────────────────────────

def youtube_choice_kb(uid: str) -> InlineKeyboardMarkup:
    """Выбор формата: аудио или видео."""
    kb = InlineKeyboardBuilder()
    kb.button(text="🎵  MP3 Аудио",  callback_data=f"yt|audio|{uid}")
    kb.button(text="🎬  Видео",      callback_data=f"yt|video|{uid}")
    kb.adjust(2)
    return kb.as_markup()


def youtube_quality_kb(uid: str) -> InlineKeyboardMarkup:
    """Выбор качества видео."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📱  360p",          callback_data=f"yt|quality|{uid}|360p")
    kb.button(text="📺  480p",          callback_data=f"yt|quality|{uid}|480p")
    kb.button(text="🖥  720p HD",       callback_data=f"yt|quality|{uid}|720p")
    kb.button(text="🖥  1080p FHD",     callback_data=f"yt|quality|{uid}|1080p")
    kb.button(text="⭐  Лучшее качество", callback_data=f"yt|quality|{uid}|best")
    kb.button(text="◀️  Назад",          callback_data=f"yt|back|{uid}")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


# ─── Instagram ────────────────────────────────────────────────────────────────

def instagram_choice_kb(uid: str) -> InlineKeyboardMarkup:
    """Выбор типа медиа для скачивания."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📥  Всё (фото + видео)", callback_data=f"ig|all|{uid}")
    kb.button(text="🖼  Только фото",        callback_data=f"ig|photo|{uid}")
    kb.button(text="🎬  Только видео",       callback_data=f"ig|video|{uid}")
    kb.button(text="❌  Отмена",             callback_data="cancel")
    kb.adjust(1, 2, 1)
    return kb.as_markup()


# ─── Общие ────────────────────────────────────────────────────────────────────

def cancel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="cancel")
    return kb.as_markup()


def help_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📸 Instagram",  callback_data="help|instagram")
    kb.button(text="▶️ YouTube",    callback_data="help|youtube")
    kb.button(text="❓ О боте",     callback_data="help|about")
    kb.adjust(2, 1)
    return kb.as_markup()