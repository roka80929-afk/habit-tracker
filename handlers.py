"""
Хендлеры бота: главное меню, добавление/удаление привычек, выбор времени
напоминания, отметки выполнения, мини-апп.
"""

import os

from aiogram import Router, F
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
)

import database as db

router = Router()

WEBAPP_URL = os.getenv("WEBAPP_URL", "")

COMMON_TIMES = ["07:00", "08:00", "09:00", "12:00", "18:00", "20:00", "21:00", "22:00"]


class AddHabit(StatesGroup):
    waiting_name = State()
    waiting_time = State()
    waiting_custom_time = State()


class ChangeTime(StatesGroup):
    waiting_habit = State()
    waiting_time = State()
    waiting_custom_time = State()


class DeleteHabit(StatesGroup):
    waiting_habit = State()
    waiting_confirm = State()


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Мои привычки")],
            [KeyboardButton(text="➕ Добавить привычку"), KeyboardButton(text="🗑 Удалить привычку")],
            [KeyboardButton(text="⏰ Изменить время"), KeyboardButton(text="📊 Статистика")],
        ],
        resize_keyboard=True,
    )


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


def time_picker_keyboard(prefix: str) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for t in COMMON_TIMES:
        row.append(InlineKeyboardButton(text=t, callback_data=f"{prefix}:{t}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✏️ Ввести своё время", callback_data=f"{prefix}:custom")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def habits_list_keyboard(habits: list[dict], prefix: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{h['name']} ({h['reminder_time']})", callback_data=f"{prefix}:{h['id']}")]
        for h in habits
    ]
    rows.append([InlineKeyboardButton(text="Отмена", callback_data=f"{prefix}:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def is_valid_time(text: str) -> bool:
    parts = text.strip().split(":")
    if len(parts) != 2:
        return False
    h, m = parts
    if not (h.isdigit() and m.isdigit()):
        return False
    h, m = int(h), int(m)
    return 0 <= h <= 23 and 0 <= m <= 59


def normalize_time(text: str) -> str:
    h, m = text.strip().split(":")
    return f"{int(h):02d}:{int(m):02d}"


# ---------- Старт и меню ----------

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await db.ensure_user(message.from_user.id)
    text = (
        "Привет! Я помогу тебе отслеживать привычки 💪\n\n"
        "Пользуйся кнопками внизу экрана, чтобы добавлять привычки, "
        "отмечать выполнение, менять время напоминаний и удалять привычки."
    )
    await message.answer(text, reply_markup=main_menu_keyboard())
    if WEBAPP_URL:
        await message.answer("А тут — статистика и heatmap:", reply_markup=webapp_keyboard())


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())


# ---------- Мои привычки / отметки ----------

@router.message(F.text == "📝 Мои привычки")
@router.message(Command("habits"))
async def cmd_habits(message: Message, state: FSMContext) -> None:
    await state.clear()
    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer("У тебя пока нет привычек. Нажми «➕ Добавить привычку».")
        return
    await message.answer("Твои привычки на сегодня:")
    for h in habits:
        text = (
            f"«{h['name']}» — стрик {h['streak']} 🔥 (лучший: {h['best_streak']})\n"
            f"Напоминание в {h['reminder_time']}"
        )
        await message.answer(text, reply_markup=habit_row_keyboard(h["id"]))


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


# ---------- Статистика / мини-апп ----------

@router.message(F.text == "📊 Статистика")
@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext) -> None:
    await state.clear()
    kb = webapp_keyboard()
    if kb is None:
        await message.answer("Мини-апп ещё не настроен (не указан WEBAPP_URL).")
        return
    await message.answer("Открой мини-апп, чтобы увидеть heatmap и статистику:", reply_markup=kb)


# ---------- Добавление привычки ----------

@router.message(F.text == "➕ Добавить привычку")
@router.message(Command("new"))
async def cmd_new_start(message: Message, state: FSMContext, command: CommandObject | None = None) -> None:
    if command and command.args:
        name = command.args.strip()
        await state.update_data(habit_name=name)
        await state.set_state(AddHabit.waiting_time)
        await message.answer(
            f"Привычка «{name}». Во сколько напоминать?",
            reply_markup=time_picker_keyboard("addtime"),
        )
        return

    await state.set_state(AddHabit.waiting_name)
    await message.answer("Как назвать привычку? Напиши в ответном сообщении, например: читать")


@router.message(StateFilter(AddHabit.waiting_name))
async def add_habit_got_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым. Напиши название привычки:")
        return
    await state.update_data(habit_name=name)
    await state.set_state(AddHabit.waiting_time)
    await message.answer(
        f"Привычка «{name}». Во сколько напоминать?",
        reply_markup=time_picker_keyboard("addtime"),
    )


@router.callback_query(StateFilter(AddHabit.waiting_time), F.data.startswith("addtime:"))
async def add_habit_time_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    if value == "custom":
        await state.set_state(AddHabit.waiting_custom_time)
        await callback.message.edit_text("Напиши время в формате ЧЧ:ММ, например 09:30")
        await callback.answer()
        return

    data = await state.get_data()
    name = data.get("habit_name", "привычка")
    await db.add_habit(callback.from_user.id, name, reminder_time=value)
    await state.clear()
    await callback.message.edit_text(f"Добавил привычку «{name}» ✅\nНапоминание в {value}.")
    await callback.answer()


@router.message(StateFilter(AddHabit.waiting_custom_time))
async def add_habit_custom_time(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not is_valid_time(text):
        await message.answer("Не похоже на время. Формат ЧЧ:ММ, например 09:30. Попробуй ещё раз:")
        return
    time_str = normalize_time(text)
    data = await state.get_data()
    name = data.get("habit_name", "привычка")
    await db.add_habit(message.from_user.id, name, reminder_time=time_str)
    await state.clear()
    await message.answer(f"Добавил привычку «{name}» ✅\nНапоминание в {time_str}.", reply_markup=main_menu_keyboard())


# ---------- Изменение времени напоминания ----------

@router.message(F.text == "⏰ Изменить время")
async def change_time_start(message: Message, state: FSMContext) -> None:
    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer("У тебя пока нет привычек.")
        return
    await state.set_state(ChangeTime.waiting_habit)
    await message.answer("Для какой привычки изменить время?", reply_markup=habits_list_keyboard(habits, "chtime_h"))


@router.callback_query(StateFilter(ChangeTime.waiting_habit), F.data.startswith("chtime_h:"))
async def change_time_habit_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    if value == "cancel":
        await state.clear()
        await callback.message.edit_text("Отменено.")
        await callback.answer()
        return
    await state.update_data(habit_id=int(value))
    await state.set_state(ChangeTime.waiting_time)
    await callback.message.edit_text("Выбери новое время:", reply_markup=time_picker_keyboard("chtime_t"))
    await callback.answer()


@router.callback_query(StateFilter(ChangeTime.waiting_time), F.data.startswith("chtime_t:"))
async def change_time_time_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    if value == "custom":
        await state.set_state(ChangeTime.waiting_custom_time)
        await callback.message.edit_text("Напиши новое время в формате ЧЧ:ММ, например 09:30")
        await callback.answer()
        return

    data = await state.get_data()
    habit_id = data.get("habit_id")
    await db.set_reminder_time(habit_id, value)
    await state.clear()
    await callback.message.edit_text(f"Готово! Новое время напоминания: {value}.")
    await callback.answer()


@router.message(StateFilter(ChangeTime.waiting_custom_time))
async def change_time_custom(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not is_valid_time(text):
        await message.answer("Не похоже на время. Формат ЧЧ:ММ, например 09:30. Попробуй ещё раз:")
        return
    time_str = normalize_time(text)
    data = await state.get_data()
    habit_id = data.get("habit_id")
    await db.set_reminder_time(habit_id, time_str)
    await state.clear()
    await message.answer(f"Готово! Новое время напоминания: {time_str}.", reply_markup=main_menu_keyboard())


# ---------- Удаление привычки ----------

@router.message(F.text == "🗑 Удалить привычку")
async def delete_habit_start(message: Message, state: FSMContext) -> None:
    habits = await db.list_habits(message.from_user.id)
    if not habits:
        await message.answer("У тебя пока нет привычек.")
        return
    await state.set_state(DeleteHabit.waiting_habit)
    await message.answer("Какую привычку удалить?", reply_markup=habits_list_keyboard(habits, "delh"))


@router.callback_query(StateFilter(DeleteHabit.waiting_habit), F.data.startswith("delh:"))
async def delete_habit_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    if value == "cancel":
        await state.clear()
        await callback.message.edit_text("Отменено.")
        await callback.answer()
        return
    habit = await db.get_habit(int(value))
    await state.update_data(habit_id=int(value))
    await state.set_state(DeleteHabit.waiting_confirm)
    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, удалить", callback_data="delh_confirm:yes"),
                InlineKeyboardButton(text="Отмена", callback_data="delh_confirm:no"),
            ]
        ]
    )
    await callback.message.edit_text(
        f"Точно удалить «{habit['name']}»? Стрик и история пропадут из списка.",
        reply_markup=confirm_kb,
    )
    await callback.answer()


@router.callback_query(StateFilter(DeleteHabit.waiting_confirm), F.data.startswith("delh_confirm:"))
async def delete_habit_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    data = await state.get_data()
    habit_id = data.get("habit_id")
    await state.clear()
    if value == "yes":
        await db.archive_habit(habit_id)
        await callback.message.edit_text("Привычка удалена.")
    else:
        await callback.message.edit_text("Отменено.")
    await callback.answer()
