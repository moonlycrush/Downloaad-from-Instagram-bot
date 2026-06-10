"""database.py - async SQLite wrapper with users and admins"""
import aiosqlite
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "data/bot.db"


class Database:
    def __init__(self, database_path: str | None = None):
        self._db_path = database_path or DEFAULT_DB_PATH
        self._conn: aiosqlite.Connection | None = None

    async def connect(self):
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._conn.commit()
        logger.info("Connected to SQLite database at %s", self._db_path)

    async def create_tables(self):
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                join_date TEXT,
                download_count INTEGER DEFAULT 0,
                instagram_downloads INTEGER DEFAULT 0,
                youtube_downloads INTEGER DEFAULT 0,
                last_activity TEXT
            );
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_at TEXT
            );
            """
        )
        await self._conn.commit()
        logger.info("Ensured tables exist")

    async def upsert_user(self, user_id: int, username: str, first_name: str, join_date: str, last_activity: str):
        await self._conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, join_date, last_activity)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              username=excluded.username,
              first_name=excluded.first_name,
              last_activity=excluded.last_activity;
            """,
            (user_id, username, first_name, join_date, last_activity),
        )
        await self._conn.commit()

    async def increment_download(self, user_id: int, kind: str = "total"):
        if kind == "instagram":
            await self._conn.execute(
                "UPDATE users SET instagram_downloads = instagram_downloads + 1, download_count = download_count + 1 WHERE user_id = ?",
                (user_id,),
            )
        elif kind == "youtube":
            await self._conn.execute(
                "UPDATE users SET youtube_downloads = youtube_downloads + 1, download_count = download_count + 1 WHERE user_id = ?",
                (user_id,),
            )
        else:
            await self._conn.execute(
                "UPDATE users SET download_count = download_count + 1 WHERE user_id = ?",
                (user_id,),
            )
        await self._conn.commit()

    # Admin helpers
    async def add_admin(self, user_id: int):
        now = datetime.utcnow().isoformat()
        await self._conn.execute(
            "INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?);", (user_id, now)
        )
        await self._conn.commit()

    async def remove_admin(self, user_id: int):
        await self._conn.execute("DELETE FROM admins WHERE user_id = ?;", (user_id,))
        await self._conn.commit()

    async def is_admin(self, user_id: int) -> bool:
        cur = await self._conn.execute("SELECT 1 FROM admins WHERE user_id = ? LIMIT 1;", (user_id,))
        row = await cur.fetchone()
        return bool(row)

    async def admins_count(self) -> int:
        cur = await self._conn.execute("SELECT COUNT(*) FROM admins;")
        row = await cur.fetchone()
        return row[0] if row else 0

    async def list_admins(self):
        cur = await self._conn.execute("SELECT user_id, added_at FROM admins ORDER BY added_at DESC;")
        rows = await cur.fetchall()
        return rows

    # Stats & users
    async def get_stats(self):
        cur = await self._conn.execute("SELECT COUNT(*) FROM users;")
        total = (await cur.fetchone())[0]
        cur = await self._conn.execute("SELECT SUM(youtube_downloads) FROM users;")
        youtube_sum = (await cur.fetchone())[0] or 0
        cur = await self._conn.execute("SELECT SUM(instagram_downloads) FROM users;")
        insta_sum = (await cur.fetchone())[0] or 0
        return {"total_users": total, "youtube_downloads": youtube_sum, "instagram_downloads": insta_sum}

    async def list_users(self, limit=100):
        cur = await self._conn.execute(
            "SELECT user_id, username, first_name, download_count, last_activity FROM users ORDER BY join_date DESC LIMIT ?;",
            (limit,),
        )
        rows = await cur.fetchall()
        return rows

    async def close(self):
        if self._conn:
            await self._conn.close()
            logger.info("DB connection closed")

    async def get_user_stats(self, user_id: int) -> dict:
        cur = await self._conn.execute(
            "SELECT download_count, instagram_downloads, youtube_downloads FROM users WHERE user_id = ?;",
            (user_id,),
        )
        row = await cur.fetchone()
        if row:
            return {"download_count": row[0], "instagram_downloads": row[1], "youtube_downloads": row[2]}
        return {"download_count": 0, "instagram_downloads": 0, "youtube_downloads": 0}