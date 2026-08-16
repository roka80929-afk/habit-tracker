state.update_data(habit_name=name)
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
