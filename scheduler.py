from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from storage import Storage
from utils import SummaryData, build_summary_text, compute_next_ping

logger = logging.getLogger(__name__)


async def check_and_ping_chats(application, storage: Storage) -> None:
    now = datetime.now(UTC)
    metas = await asyncio.to_thread(storage.due_chat_metas, now)
    if not metas:
        return

    for meta in metas:
        chat_id = meta.chat_id
        stats = await asyncio.to_thread(storage.count_stats, chat_id)
        random_wish = await asyncio.to_thread(storage.random_open_wish, chat_id)
        nearest = await asyncio.to_thread(storage.nearest_with_date, chat_id)
        summary = SummaryData(
            total=stats.get("total", 0),
            by_horizon=stats.get("by_horizon", {}),
            nearest=nearest,
            random_wish=random_wish,
        )
        text = build_summary_text(summary)
        try:
            await application.bot.send_message(chat_id=chat_id, text=text)
        except Exception:  # pragma: no cover - log errors
            logger.exception("Не удалось отправить сводку в чат %s", chat_id)
        next_ping = compute_next_ping(now, meta.timezone, days=14)
        await asyncio.to_thread(storage.update_chat_meta, chat_id, next_ping_at=next_ping)


def init_scheduler(application, storage: Storage) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=UTC)

    async def runner():
        await check_and_ping_chats(application, storage)

    scheduler.add_job(
        lambda: asyncio.create_task(runner()),
        "interval",
        hours=6,
        next_run_time=datetime.now(UTC),
    )
    scheduler.start()
    return scheduler


__all__ = ["init_scheduler", "check_and_ping_chats"]
