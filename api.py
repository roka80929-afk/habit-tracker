"""
FastAPI-сервер: отдаёт JSON для мини-аппа (heatmap, статистика, XP/уровень)
и раздаёт статические файлы мини-аппа из папки webapp/.

ВАЖНО (безопасность, для продакшена):
Сейчас user_id принимается как query-параметр напрямую от фронтенда.
Это ок для MVP/личного пользования, но НЕ безопасно для публичного бота —
любой человек сможет запросить чужие данные, подставив чужой user_id.
Для продакшена нужно валидировать `Telegram.WebApp.initData` (там есть
подписанный хэш) на бэкенде и брать user_id только из него.
Подробности: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import database as db

app = FastAPI(title="Habit Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    await db.init_db()


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/dashboard")
async def dashboard(user_id: int = Query(...)) -> dict:
    heatmap = await db.get_heatmap_data(user_id)
    user_stats = await db.get_user_stats(user_id)
    return {**heatmap, **user_stats}


webapp_dir = Path(__file__).parent / "webapp"
app.mount("/", StaticFiles(directory=webapp_dir, html=True), name="webapp")

