"""
Хендлеры команд бота: /start, /new, /habits, отметки через инлайн-кнопки, /stats.
"""

import os

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)

import database as db

router = Router()

WEBAPP_URL = os.getenv("WEBAPP_URL", "")


def habit_row_keyboard(habit_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Готово", callback_data=f"done:{habit_id}"),
                InlineKeyboardButton(text="❌ Пропуск", callback_data=f"skip:{habit_id}"),
            ]
        ]
    )


def webapp_keyboard() -> InlineKeyboardMarkup | None:
    if not WEBAPP_URL:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Открыть статистику", web_app=WebAppInfo(url=WEBAPP_URL))]
        ]
    )


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await db.ensure_user(message.from_user.id)
    text = (
        "Привет! Я помогу тебе отслеживать привычки 💪\n\n"
        "• /new <название> — добавить привычку (например: /new читать)\n"
        "• /habits — список привычек и отметка на сегодня\n"
        "• /stats — открыть статистику и heatmap\n\n"
        "Каждый день я буду напоминать отметить прогресс."
    )
    await message.answer(text, reply_markup=webapp_keyboard())


@router.message(Command("new"))
async def cmd_new(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.answer("Укажи название привычки: /new читать")
        return
    name = command.args.strip()
    habit_id = await db.add_habit(message.from_user.id, name)
    await message.answer(f"Добавил привычку «{name}» ✅\nБуду напоминать про неё каждый день.")


@router.message(Command("habits"))
async def cmd_habits(message: Message) -> None:
    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer("У тебя пока нет привычек. Добавь через /new <название>.")
        return
    await message.answer("Твои привычки на сегодня:")
    for h in habits:
        text = f"«{h['name']}» — стрик {h['streak']} 🔥 (лучший: {h['best_streak']})"
        await message.answer(text, reply_markup=habit_row_keyboard(h["id"]))


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    kb = webapp_keyboard()
    if kb is None:
        await message.answer(
            "Мини-апп ещё не настроен (не указан WEBAPP_URL в .env)."
        )
        return
    await message.answer("Открой мини-апп, чтобы увидеть heatmap и статистику:", reply_markup=kb)


@router.callback_query(F.data.startswith("done:"))
async def on_done(callback: CallbackQuery) -> None:
    habit_id = int(callback.data.split(":")[1])
    result = await db.checkin(habit_id, done=True)
    await callback.answer(f"Отмечено! Стрик: {result['streak']} 🔥 (+{result['xp_delta']} XP)")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("skip:"))
async def on_skip(callback: CallbackQuery) -> None:
    habit_id = int(callback.data.split(":")[1])
    await db.checkin(habit_id, done=False)
    await callback.answer("Записал пропуск. Стрик сброшен, но завтра можно начать снова 💪")
    await callback.message.edit_reply_markup(reply_markup=None)

