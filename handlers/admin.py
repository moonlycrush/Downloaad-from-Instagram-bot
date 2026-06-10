"""handlers/admin.py — Панель администратора"""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)
admin_router = Router()


async def _get_db(message: Message):
    return getattr(message.bot, "db", None)


def _admin_panel_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика",      callback_data="adm|stats")
    kb.button(text="👥 Пользователи",    callback_data="adm|users")
    kb.button(text="➕ Добавить админа", callback_data="adm|add_hint")
    kb.button(text="➖ Удалить админа",  callback_data="adm|rem_hint")
    kb.adjust(2)
    return kb.as_markup()


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    db = await _get_db(message)
    if not db:
        await message.reply("❌ <b>База данных недоступна.</b>")
        return

    count = await db.admins_count()
    if count == 0:
        await message.reply(
            "⚠️ <b>Администраторы не назначены.</b>\n\n"
            "Отправьте /setup_admin чтобы стать первым администратором."
        )
        return

    is_admin = await db.is_admin(message.from_user.id)
    if not is_admin:
        await message.reply("🚫 <b>Доступ запрещён.</b> Вы не являетесь администратором.")
        return

    await message.reply(
        "⚙️ <b>Панель администратора</b>\n\n"
        f"👤 Администраторов: <b>{count}</b>\n\n"
        "Доступные команды:\n"
        "  /stats — статистика бота\n"
        "  /users — список пользователей\n"
        "  /add_admin &lt;id&gt; — добавить админа\n"
        "  /remove_admin &lt;id&gt; — удалить админа\n"
        "  /broadcast &lt;текст&gt; — рассылка всем",
        reply_markup=_admin_panel_kb(),
    )


@admin_router.message(Command("setup_admin"))
async def cmd_setup_admin(message: Message):
    db = await _get_db(message)
    if not db:
        await message.reply("❌ База данных недоступна.")
        return

    count = await db.admins_count()
    if count == 0:
        await db.add_admin(message.from_user.id)
        await message.reply(
            "✅ <b>Вы успешно назначены администратором!</b>\n\n"
            f"🆔 Ваш ID: <code>{message.from_user.id}</code>\n\n"
            "Используйте /admin для управления ботом."
        )
        logger.info("Bootstrap admin added: %s", message.from_user.id)
        return

    is_admin = await db.is_admin(message.from_user.id)
    if not is_admin:
        await message.reply("🚫 Администраторы уже назначены. Вы не можете стать первым.")
        return
    await message.reply("ℹ️ Вы уже являетесь администратором.")


@admin_router.message(Command("add_admin"))
async def cmd_add_admin(message: Message):
    db = await _get_db(message)
    if not db:
        await message.reply("❌ База данных недоступна.")
        return
    if not await db.is_admin(message.from_user.id):
        await message.reply("🚫 Доступ запрещён.")
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply("ℹ️ Использование: /add_admin <code>&lt;user_id&gt;</code>")
        return
    try:
        new_id = int(parts[1])
        await db.add_admin(new_id)
        await message.reply(f"✅ Пользователь <code>{new_id}</code> назначен администратором.")
    except ValueError:
        await message.reply("❌ Неверный формат ID. Используйте числовой ID.")
    except Exception:
        logger.exception("add_admin error")
        await message.reply("❌ Произошла ошибка.")


@admin_router.message(Command("remove_admin"))
async def cmd_remove_admin(message: Message):
    db = await _get_db(message)
    if not db:
        await message.reply("❌ База данных недоступна.")
        return
    if not await db.is_admin(message.from_user.id):
        await message.reply("🚫 Доступ запрещён.")
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply("ℹ️ Использование: /remove_admin <code>&lt;user_id&gt;</code>")
        return
    try:
        rem_id = int(parts[1])
        await db.remove_admin(rem_id)
        await message.reply(f"✅ Пользователь <code>{rem_id}</code> удалён из администраторов.")
    except ValueError:
        await message.reply("❌ Неверный формат ID.")
    except Exception:
        logger.exception("remove_admin error")
        await message.reply("❌ Произошла ошибка.")


@admin_router.message(Command("stats"))
async def cmd_stats(message: Message):
    db = await _get_db(message)
    if not db or not await db.is_admin(message.from_user.id):
        return
    try:
        stats = await db.get_stats()
        await message.reply(
            "📊 <b>Статистика бота</b>\n\n"
            f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
            f"📸 Instagram загрузок: <b>{stats['instagram_downloads']}</b>\n"
            f"▶️ YouTube загрузок: <b>{stats['youtube_downloads']}</b>\n"
            f"📥 Всего загрузок: <b>{stats['instagram_downloads'] + stats['youtube_downloads']}</b>"
        )
    except Exception:
        logger.exception("stats error")
        await message.reply("❌ Ошибка получения статистики.")


@admin_router.message(Command("users"))
async def cmd_users(message: Message):
    db = await _get_db(message)
    if not db or not await db.is_admin(message.from_user.id):
        return
    try:
        users = await db.list_users(limit=200)
        lines = []
        for row in users:
            user_id, username, first_name, downloads, last_activity = row
            name = first_name or username or str(user_id)
            uname = f"@{username}" if username else "—"
            lines.append(f"👤 {name} ({uname}) | 📥 {downloads} | 🕐 {str(last_activity)[:10]}")
        if not lines:
            await message.reply("📭 Пользователи не найдены.")
        else:
            chunk_size = 4000
            msg = ""
            for line in lines:
                if len(msg) + len(line) + 1 > chunk_size:
                    await message.reply(msg)
                    msg = ""
                msg += line + "\n"
            if msg:
                await message.reply(msg)
    except Exception:
        logger.exception("users error")
        await message.reply("❌ Ошибка получения списка пользователей.")


@admin_router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    db = await _get_db(message)
    if not db or not await db.is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(" ", 1)
    if len(parts) < 2:
        await message.reply("ℹ️ Использование: /broadcast <code>&lt;сообщение&gt;</code>")
        return
    text  = parts[1]
    users = await db.list_users(limit=10000)
    sent  = 0
    failed = 0
    for u in users:
        try:
            await message.bot.send_message(chat_id=u[0], text=text)
            sent += 1
        except Exception:
            failed += 1
    await message.reply(
        f"📢 <b>Рассылка завершена!</b>\n\n"
        f"✅ Отправлено: <b>{sent}</b>\n"
        f"❌ Ошибок: <b>{failed}</b>"
    )