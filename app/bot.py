"""Main bot application factory."""
from __future__ import annotations

import asyncio
import logging
from datetime import time

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
import redis.asyncio as redis
from aiohttp import web
from sqlalchemy import select

from .config import settings
from .routers import admin, auth, checkins, group, reports, settings as settings_router
from .db import async_session_factory
from .models import ChatSettings
from .scheduler import ShiftScheduler
from .services.notifications import NotificationService

logger = logging.getLogger(__name__)


async def create_storage() -> BaseStorage:
    try:
        redis_client = redis.from_url(settings.redis_url)
        storage = RedisStorage(redis=redis_client, key_builder=DefaultKeyBuilder(with_destiny=True))
        await redis_client.ping()
        logger.info("Using Redis storage")
        return storage
    except Exception:
        logger.warning("Falling back to in-memory FSM storage")
        return MemoryStorage()


async def _start_healthcheck() -> web.AppRunner:
    app = web.Application()

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="OK")

    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    return runner


async def create_app() -> Dispatcher:
    logging.basicConfig(level=settings.log_level)
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = await create_storage()
    dp = Dispatcher(storage=storage)
    notification_service = NotificationService(bot)
    scheduler = ShiftScheduler(notification_service)
    health_runner: web.AppRunner | None = None

    @dp.startup()
    async def on_startup() -> None:  # pragma: no cover
        scheduler.start()
        nonlocal health_runner
        health_runner = await _start_healthcheck()
        async with async_session_factory() as session:
            exists = await session.execute(
                select(ChatSettings).where(ChatSettings.chat_id.is_(None))
            )
            if exists.scalar_one_or_none() is None:
                session.add(
                    ChatSettings(
                        chat_id=None,
                        morning_start=time(6, 0),
                        morning_end=time(11, 0),
                        evening_start=time(16, 0),
                        evening_end=time(23, 0),
                        alerts_enabled=True,
                        include_weekends=True,
                        timezone=settings.timezone,
                    )
                )
                await session.commit()
        logger.info("Bot started")

    @dp.shutdown()
    async def on_shutdown() -> None:  # pragma: no cover
        await scheduler.shutdown()
        if health_runner:
            await health_runner.cleanup()
        await bot.session.close()
        logger.info("Bot stopped")

    dp.include_routers(
        group.router,
        auth.router,
        checkins.router,
        reports.router,
        settings_router.router,
        admin.router,
    )
    dp.workflow_data.update({"bot": bot, "scheduler": scheduler})
    return dp


async def run_polling() -> None:
    dp = await create_app()
    bot = dp.workflow_data["bot"]
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(run_polling())


if __name__ == "__main__":  # pragma: no cover
    main()
