"""
Планировщик ежедневных напоминаний. Раз в минуту проверяет, у каких привычек
сейчас настало время напоминания (по полю reminder_time, формат "HH:MM"),
и шлёт пользователю сообщение с кнопками Готово/Пропуск.
"""

import datetime as dt

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db
from handlers import habit_row_keyboard

_scheduler = AsyncIOScheduler()


async def _check_and_send(bot: Bot) -> None:
    now_hm = dt.datetime.now().strftime("%H:%M")

    import aiosqlite

    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT id, user_id, name, streak FROM habits "
            "WHERE archived = 0 AND reminder_time = ?",
            (now_hm,),
        )
        habits = [dict(r) for r in await cur.fetchall()]

    for h in habits:
        try:
            await bot.send_message(
                h["user_id"],
                f"⏰ Напоминание: «{h['name']}» — отметь выполнение (стрик: {h['streak']} 🔥)",
                reply_markup=habit_row_keyboard(h["id"]),
            )
        except Exception:
            # пользователь мог заблокировать бота — просто пропускаем
            continue


def start_scheduler(bot: Bot) -> None:
    _scheduler.add_job(_check_and_send, "cron", minute="*", args=[bot])
    _scheduler.start()

