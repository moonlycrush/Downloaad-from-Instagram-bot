"""keyboards/buttons.py - Главное reply-меню"""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📥 Скачать видео"),
                KeyboardButton(text="ℹ️ Помощь"),
            ],
            [
                KeyboardButton(text="📊 Статистика"),
                KeyboardButton(text="👤 Профиль"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Отправьте ссылку или выберите действие...",
    )