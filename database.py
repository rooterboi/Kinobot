"""SQLite ma'lumotlar bazasi (aiosqlite). Barcha jadvallar bot_id bo'yicha ajratilgan."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from utils import now_str, today_str

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS bots(
    bot_id INTEGER PRIMARY KEY,
    token TEXT NOT NULL DEFAULT '',
    username TEXT,
    owner_id INTEGER NOT NULL DEFAULT 0,
    is_main INTEGER NOT NULL DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS users(
    bot_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    full_name TEXT,
    username TEXT,
    joined_at TEXT,
    last_active TEXT,
    PRIMARY KEY(bot_id, user_id)
);
CREATE TABLE IF NOT EXISTS movies(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    file_id TEXT NOT NULL,
    file_type TEXT NOT NULL DEFAULT 'video',
    title TEXT NOT NULL,
    year TEXT, quality TEXT, country TEXT, language TEXT, genre TEXT,
    views INTEGER NOT NULL DEFAULT 0,
    created_at TEXT,
    UNIQUE(bot_id, code)
);
CREATE TABLE IF NOT EXISTS channels(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    title TEXT,
    link TEXT,
    UNIQUE(bot_id, chat_id)
);
CREATE TABLE IF NOT EXISTS series(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    title TEXT NOT NULL,
    year TEXT, quality TEXT, country TEXT, language TEXT, genre TEXT,
    views INTEGER NOT NULL DEFAULT 0,
    created_at TEXT,
    UNIQUE(bot_id, code)
);
CREATE TABLE IF NOT EXISTS episodes(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id INTEGER NOT NULL,
    number INTEGER NOT NULL,
    file_id TEXT NOT NULL,
    file_type TEXT NOT NULL DEFAULT 'video',
    created_at TEXT,
    UNIQUE(series_id, number)
);
CREATE TABLE IF NOT EXISTS settings(
    bot_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY(bot_id, key)
);
"""

MOVIE_FIELDS = {"title", "year", "quality", "country", "language", "genre", "code"}
SERIES_FIELDS = MOVIE_FIELDS


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    async def _run(self, sql: str, params: tuple = (), fetch: Optional[str] = None) -> Any:
        assert self._conn is not None, "Database.init() chaqirilmagan"
        async with self._lock:
            cur = await self._conn.execute(sql, params)
            try:
                if fetch == "one":
                    row = await cur.fetchone()
                    return dict(row) if row else None
                if fetch == "all":
                    return [dict(r) for r in await cur.fetchall()]
                await self._conn.commit()
                return cur.rowcount
            finally:
                await cur.close()

    # ---------------- bots ----------------
    async def upsert_bot(self, bot_id: int, token: str, username: str, owner_id: int, is_main: int) -> None:
        await self._run(
            "INSERT INTO bots(bot_id,token,username,owner_id,is_main,created_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(bot_id) DO UPDATE SET token=excluded.token, username=excluded.username, "
            "owner_id=excluded.owner_id, is_main=excluded.is_main",
            (bot_id, token, username, owner_id, is_main, now_str()),
        )

    async def get_bot(self, bot_id: int) -> Optional[dict]:
        return await self._run("SELECT * FROM bots WHERE bot_id=?", (bot_id,), "one")

    async def list_child_bots(self) -> list[dict]:
        return await self._run("SELECT * FROM bots WHERE is_main=0", (), "all")

    async def delete_bot(self, bot_id: int) -> None:
        await self._run("DELETE FROM bots WHERE bot_id=?", (bot_id,))

    # ---------------- users ----------------
    async def touch_user(self, bot_id: int, user_id: int, full_name: str, username: Optional[str]) -> None:
        now = now_str()
        await self._run(
            "INSERT INTO users(bot_id,user_id,full_name,username,joined_at,last_active) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(bot_id,user_id) DO UPDATE SET full_name=excluded.full_name, "
            "username=excluded.username, last_active=excluded.last_active",
            (bot_id, user_id, full_name, username, now, now),
        )

    async def all_user_ids(self, bot_id: int) -> list[int]:
        rows = await self._run("SELECT user_id FROM users WHERE bot_id=?", (bot_id,), "all")
        return [r["user_id"] for r in rows]

    async def stats(self, bot_id: int) -> dict:
        today = today_str()

        async def one(sql: str, params: tuple) -> int:
            row = await self._run(sql, params, "one")
            return int(list(row.values())[0]) if row else 0

        return {
            "users": await one("SELECT COUNT(*) FROM users WHERE bot_id=?", (bot_id,)),
            "active_today": await one(
                "SELECT COUNT(*) FROM users WHERE bot_id=? AND last_active LIKE ? || '%'", (bot_id, today)),
            "new_today": await one(
                "SELECT COUNT(*) FROM users WHERE bot_id=? AND joined_at LIKE ? || '%'", (bot_id, today)),
            "movies": await one("SELECT COUNT(*) FROM movies WHERE bot_id=?", (bot_id,)),
            "views": await one("SELECT COALESCE(SUM(views),0) FROM movies WHERE bot_id=?", (bot_id,)),
            "channels": await one("SELECT COUNT(*) FROM channels WHERE bot_id=?", (bot_id,)),
            "series": await one("SELECT COUNT(*) FROM series WHERE bot_id=?", (bot_id,)),
            "episodes": await one(
                "SELECT COUNT(*) FROM episodes WHERE series_id IN (SELECT id FROM series WHERE bot_id=?)",
                (bot_id,)),
        }

    # ---------------- movies ----------------
    async def add_movie(self, bot_id: int, m: dict) -> bool:
        try:
            await self._run(
                "INSERT INTO movies(bot_id,code,file_id,file_type,title,year,quality,country,language,genre,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (bot_id, m["code"], m["file_id"], m["file_type"], m["title"], m["year"], m["quality"],
                 m["country"], m["language"], m["genre"], now_str()),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    async def get_movie(self, bot_id: int, code: str) -> Optional[dict]:
        return await self._run("SELECT * FROM movies WHERE bot_id=? AND code=?", (bot_id, code), "one")

    async def delete_movie(self, bot_id: int, code: str) -> bool:
        return (await self._run("DELETE FROM movies WHERE bot_id=? AND code=?", (bot_id, code))) > 0

    async def update_movie_field(self, bot_id: int, code: str, field: str, value: str) -> bool:
        if field not in MOVIE_FIELDS:
            raise ValueError("Ruxsat etilmagan maydon")
        try:
            return (await self._run(
                f"UPDATE movies SET {field}=? WHERE bot_id=? AND code=?", (value, bot_id, code))) > 0
        except sqlite3.IntegrityError:
            return False

    async def list_movies(self, bot_id: int, limit: int = 40) -> list[dict]:
        return await self._run(
            "SELECT code,title,year,genre FROM movies WHERE bot_id=? ORDER BY id DESC LIMIT ?",
            (bot_id, limit), "all")

    async def search_movies(self, bot_id: int, query: str, limit: int = 10) -> list[dict]:
        like = f"%{query}%"
        return await self._run(
            "SELECT code,title,year FROM movies WHERE bot_id=? AND (title LIKE ? OR genre LIKE ?) LIMIT ?",
            (bot_id, like, like, limit), "all")

    async def inc_views(self, bot_id: int, code: str) -> None:
        await self._run("UPDATE movies SET views=views+1 WHERE bot_id=? AND code=?", (bot_id, code))

    async def next_code(self, bot_id: int) -> int:
        row = await self._run(
            "SELECT COALESCE(MAX(CAST(code AS INTEGER)),0)+1 AS n FROM movies WHERE bot_id=?", (bot_id,), "one")
        return int(row["n"]) if row else 1

    # ---------------- channels ----------------
    async def add_channel(self, bot_id: int, chat_id: int, title: str, link: str) -> bool:
        try:
            await self._run("INSERT INTO channels(bot_id,chat_id,title,link) VALUES(?,?,?,?)",
                            (bot_id, chat_id, title, link))
            return True
        except sqlite3.IntegrityError:
            return False

    async def list_channels(self, bot_id: int) -> list[dict]:
        return await self._run("SELECT * FROM channels WHERE bot_id=? ORDER BY id", (bot_id,), "all")

    async def remove_channel(self, bot_id: int, channel_id: int) -> None:
        await self._run("DELETE FROM channels WHERE bot_id=? AND id=?", (bot_id, channel_id))

    # ---------------- settings ----------------
    async def get_setting(self, bot_id: int, key: str, default: Optional[str] = None) -> Optional[str]:
        row = await self._run("SELECT value FROM settings WHERE bot_id=? AND key=?", (bot_id, key), "one")
        return row["value"] if row and row["value"] is not None else default

    async def set_setting(self, bot_id: int, key: str, value: str) -> None:
        await self._run(
            "INSERT INTO settings(bot_id,key,value) VALUES(?,?,?) "
            "ON CONFLICT(bot_id,key) DO UPDATE SET value=excluded.value", (bot_id, key, value))

    async def del_setting(self, bot_id: int, key: str) -> None:
        await self._run("DELETE FROM settings WHERE bot_id=? AND key=?", (bot_id, key))

    # ---------------- umumiy ----------------
    async def _insert(self, sql: str, params: tuple = ()) -> int:
        assert self._conn is not None
        async with self._lock:
            cur = await self._conn.execute(sql, params)
            await self._conn.commit()
            rid = cur.lastrowid
            await cur.close()
            return int(rid)

    async def code_taken(self, bot_id: int, code: str) -> bool:
        """Kod kino yoki serialda band bo'lsa True."""
        row = await self._run(
            "SELECT 1 AS x FROM movies WHERE bot_id=? AND code=? "
            "UNION SELECT 1 FROM series WHERE bot_id=? AND code=?", (bot_id, code, bot_id, code), "one")
        return row is not None

    # ---------------- seriallar ----------------
    async def add_series(self, bot_id: int, s: dict) -> Optional[int]:
        try:
            return await self._insert(
                "INSERT INTO series(bot_id,code,title,year,quality,country,language,genre,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (bot_id, s["code"], s["title"], s["year"], s["quality"], s["country"],
                 s["language"], s["genre"], now_str()))
        except sqlite3.IntegrityError:
            return None

    async def get_series(self, bot_id: int, code: str) -> Optional[dict]:
        return await self._run("SELECT * FROM series WHERE bot_id=? AND code=?", (bot_id, code), "one")

    async def get_series_by_id(self, series_id: int) -> Optional[dict]:
        return await self._run("SELECT * FROM series WHERE id=?", (series_id,), "one")

    async def delete_series(self, bot_id: int, code: str) -> bool:
        s = await self.get_series(bot_id, code)
        if not s:
            return False
        await self._run("DELETE FROM episodes WHERE series_id=?", (s["id"],))
        await self._run("DELETE FROM series WHERE id=?", (s["id"],))
        return True

    async def update_series_field(self, bot_id: int, code: str, field: str, value: str) -> bool:
        if field not in SERIES_FIELDS:
            raise ValueError("Ruxsat etilmagan maydon")
        try:
            return (await self._run(
                f"UPDATE series SET {field}=? WHERE bot_id=? AND code=?", (value, bot_id, code))) > 0
        except sqlite3.IntegrityError:
            return False

    async def list_series(self, bot_id: int, limit: int = 40) -> list[dict]:
        return await self._run(
            "SELECT s.code, s.title, s.year, s.genre, "
            "(SELECT COUNT(*) FROM episodes e WHERE e.series_id=s.id) AS eps "
            "FROM series s WHERE s.bot_id=? ORDER BY s.id DESC LIMIT ?", (bot_id, limit), "all")

    async def search_series(self, bot_id: int, query: str, limit: int = 10) -> list[dict]:
        like = f"%{query}%"
        return await self._run(
            "SELECT code,title,year FROM series WHERE bot_id=? AND (title LIKE ? OR genre LIKE ?) LIMIT ?",
            (bot_id, like, like, limit), "all")

    async def inc_series_views(self, series_id: int) -> None:
        await self._run("UPDATE series SET views=views+1 WHERE id=?", (series_id,))

    # ---------------- qismlar ----------------
    async def add_episode(self, series_id: int, file_id: str, file_type: str) -> int:
        """Keyingi qism raqami bilan atomik qo'shadi va raqamni qaytaradi."""
        assert self._conn is not None
        async with self._lock:
            cur = await self._conn.execute(
                "INSERT INTO episodes(series_id,number,file_id,file_type,created_at) "
                "SELECT ?, COALESCE(MAX(number),0)+1, ?, ?, ? FROM episodes WHERE series_id=?",
                (series_id, file_id, file_type, now_str(), series_id))
            await self._conn.commit()
            rid = cur.lastrowid
            await cur.close()
            cur2 = await self._conn.execute("SELECT number FROM episodes WHERE id=?", (rid,))
            row = await cur2.fetchone()
            await cur2.close()
            return int(row["number"])

    async def get_episode(self, series_id: int, number: int) -> Optional[dict]:
        return await self._run("SELECT * FROM episodes WHERE series_id=? AND number=?",
                               (series_id, number), "one")

    async def list_episode_numbers(self, series_id: int) -> list[int]:
        rows = await self._run("SELECT number FROM episodes WHERE series_id=? ORDER BY number",
                               (series_id,), "all")
        return [r["number"] for r in rows]

    async def delete_episode(self, series_id: int, number: int) -> bool:
        return (await self._run("DELETE FROM episodes WHERE series_id=? AND number=?",
                                (series_id, number))) > 0
