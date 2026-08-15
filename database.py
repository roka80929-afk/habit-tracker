"""
Слой работы с БД (SQLite через aiosqlite).
Хранит: пользователей (XP/уровень), привычки, ежедневные отметки (чекины).
"""

import datetime as dt
from pathlib import Path

import aiosqlite

import os
DB_PATH = Path(os.getenv("DB_PATH", str(Path(__file__).parent / "habits.db")))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    xp INTEGER NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reminder_time TEXT NOT NULL DEFAULT '20:00',
    streak INTEGER NOT NULL DEFAULT 0,
    best_streak INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    done INTEGER NOT NULL,
    UNIQUE(habit_id, date)
);
"""

XP_PER_CHECKIN = 10
XP_PER_LEVEL = 100


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def ensure_user(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
        )
        await db.commit()


async def add_habit(user_id: int, name: str, reminder_time: str = "20:00") -> int:
    await ensure_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO habits (user_id, name, created_at, reminder_time) "
            "VALUES (?, ?, ?, ?)",
            (user_id, name, dt.date.today().isoformat(), reminder_time),
        )
        await db.commit()
        return cur.lastrowid


async def list_habits(user_id: int, include_archived: bool = False) -> list[dict]:
    query = "SELECT id, name, reminder_time, streak, best_streak FROM habits WHERE user_id = ?"
    if not include_archived:
        query += " AND archived = 0"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(query, (user_id,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_habit(habit_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM habits WHERE id = ?", (habit_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def archive_habit(habit_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE habits SET archived = 1 WHERE id = ?", (habit_id,))
        await db.commit()


async def set_reminder_time(habit_id: int, reminder_time: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE habits SET reminder_time = ? WHERE id = ?", (reminder_time, habit_id)
        )
        await db.commit()


async def checkin(habit_id: int, done: bool, date: str | None = None) -> dict:
    """
    Отмечает привычку выполненной/невыполненной на указанную дату (по умолчанию сегодня).
    Пересчитывает стрик и начисляет XP. Возвращает обновлённые данные привычки + XP-дельту.
    """
    date = date or dt.date.today().isoformat()
    habit = await get_habit(habit_id)
    if habit is None:
        raise ValueError("habit not found")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO checkins (habit_id, date, done) VALUES (?, ?, ?) "
            "ON CONFLICT(habit_id, date) DO UPDATE SET done = excluded.done",
            (habit_id, date, int(done)),
        )

        new_streak = habit["streak"]
        xp_delta = 0
        if done:
            yesterday = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
            cur = await db.execute(
                "SELECT done FROM checkins WHERE habit_id = ? AND date = ?",
                (habit_id, yesterday),
            )
            prev = await cur.fetchone()
            if prev and prev[0] == 1:
                new_streak = habit["streak"] + 1
            else:
                new_streak = 1
            xp_delta = XP_PER_CHECKIN
        else:
            new_streak = 0

        best_streak = max(habit["best_streak"], new_streak)
        await db.execute(
            "UPDATE habits SET streak = ?, best_streak = ? WHERE id = ?",
            (new_streak, best_streak, habit_id),
        )

        if xp_delta:
            await db.execute(
                "UPDATE users SET xp = xp + ? WHERE user_id = ?",
                (xp_delta, habit["user_id"]),
            )
            cur = await db.execute(
                "SELECT xp FROM users WHERE user_id = ?", (habit["user_id"],)
            )
            xp_row = await cur.fetchone()
            new_level = xp_row[0] // XP_PER_LEVEL + 1
            await db.execute(
                "UPDATE users SET level = ? WHERE user_id = ?",
                (new_level, habit["user_id"]),
            )

        await db.commit()

    return {"habit_id": habit_id, "streak": new_streak, "best_streak": best_streak, "xp_delta": xp_delta}


async def get_user_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT xp, level FROM users WHERE user_id = ?", (user_id,))
        user = await cur.fetchone()
        user = dict(user) if user else {"xp": 0, "level": 1}
        return user


async def get_heatmap_data(user_id: int, days: int = 365) -> dict:
    """
    Возвращает по каждой привычке пользователя список чекинов за последние `days` дней,
    плюс общую статистику выполнения за неделю/месяц.
    """
    start_date = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, name, reminder_time, streak, best_streak FROM habits "
            "WHERE user_id = ? AND archived = 0",
            (user_id,),
        )
        habits = [dict(r) for r in await cur.fetchall()]

        result = []
        for habit in habits:
            cur = await db.execute(
                "SELECT date, done FROM checkins WHERE habit_id = ? AND date >= ? ORDER BY date",
                (habit["id"], start_date),
            )
            checkins = {r["date"]: r["done"] for r in await cur.fetchall()}
            result.append({**habit, "checkins": checkins})

        week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
        month_ago = (dt.date.today() - dt.timedelta(days=30)).isoformat()

        cur = await db.execute(
            """SELECT COUNT(*) FROM checkins c JOIN habits h ON h.id = c.habit_id
               WHERE h.user_id = ? AND c.date >= ? AND c.done = 1""",
            (user_id, week_ago),
        )
        week_done = (await cur.fetchone())[0]

        cur = await db.execute(
            """SELECT COUNT(*) FROM checkins c JOIN habits h ON h.id = c.habit_id
               WHERE h.user_id = ? AND c.date >= ? AND c.done = 1""",
            (user_id, month_ago),
        )
        month_done = (await cur.fetchone())[0]

        n_habits = len(habits) or 1
        week_pct = round(100 * week_done / (n_habits * 7), 1)
        month_pct = round(100 * month_done / (n_habits * 30), 1)

        best_habit = max(habits, key=lambda h: h["streak"], default=None)

    return {
        "habits": result,
        "week_pct": week_pct,
        "month_pct": month_pct,
        "best_habit": best_habit["name"] if best_habit else None,
    }
