"""
Точка входа. Запускает одновременно:
  1) Telegram-бота (long polling, aiogram)
  2) FastAPI-сервер (отдаёт данные и статику мини-аппа) через uvicorn

Запуск:  python main.py
Перед запуском заполни .env (см. .env.example).
"""

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv
import uvicorn

import database as db
from handlers import router
from reminders import start_scheduler
from api import app as fastapi_app

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))


async def run_bot() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан — заполни .env (см. .env.example)")

    await db.init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    start_scheduler(bot)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


async def run_api() -> None:
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=API_PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    await asyncio.gather(run_bot(), run_api())


if __name__ == "__main__":
    asyncio.run(main())

