"""APScheduler integration for periodic jobs."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Optional, Sequence

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import async_session_factory
from .models import Chat, ChatSettings, Checkin, CheckinType, DailyStat, Membership, RoleEnum
from .services.notifications import NotificationService

logger = logging.getLogger(__name__)


class SchedulerContext:
    """Container with lazy resources for scheduled tasks."""

    def __init__(self, notification_service: NotificationService) -> None:
        self.notification_service = notification_service


class ShiftScheduler:
    """Wrapper around APScheduler for bot periodic jobs."""

    def __init__(self, notification_service: NotificationService) -> None:
        self.scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
        self.ctx = SchedulerContext(notification_service)

    def start(self) -> None:
        self.scheduler.add_job(self._remind_pending_checkins, IntervalTrigger(minutes=5))
        self.scheduler.add_job(self._aggregate_daily_stats, CronTrigger(hour=0, minute=10))
        self.scheduler.start()
        logger.info("Scheduler started")

    async def shutdown(self) -> None:
        logger.info("Stopping scheduler")
        await self.scheduler.shutdown(wait=False)

    async def _remind_pending_checkins(self) -> None:
        logger.debug("Running reminder job")
        async with async_session_factory() as session:
            chats = await session.execute(select(Chat))
            for chat in chats.scalars():
                tz = pytz.timezone(chat.timezone)
                now_local = datetime.now(tz)
                settings_row = await self._get_effective_settings(session, chat.id)
                if not settings_row:
                    continue
                if not settings_row.include_weekends and now_local.weekday() >= 5:
                    continue
                window = self._determine_window(settings_row, now_local.timetz())
                if not window:
                    continue
                await self._notify_missing_checkins(session, chat, window, now_local)

    async def _notify_missing_checkins(
        self,
        session: AsyncSession,
        chat: Chat,
        window: CheckinType,
        now_local: datetime,
    ) -> None:
        logger.debug("Checking missing checkins for chat %s in window %s", chat.chat_id, window)
        memberships = await session.execute(
            select(Membership).where(
                Membership.chat_id == chat.id,
                Membership.role == RoleEnum.OPERATOR,
                Membership.authorized.is_(True),
            )
        )
        operators = memberships.scalars().all()
        if not operators:
            return
        checkins_stmt = select(Checkin).where(
            Checkin.chat_id == chat.id,
            Checkin.type == window,
            Checkin.checkin_date == now_local.date(),
        )
        checkins = await session.execute(checkins_stmt)
        done_ids = {row.user_id for row in checkins.scalars()}
        missing = [m for m in operators if m.user_id not in done_ids]
        if not missing:
            return
        await self.ctx.notification_service.send_reminder(chat, window, missing)

    async def _aggregate_daily_stats(self) -> None:
        logger.info("Aggregating daily stats")
        async with async_session_factory() as session:
            chats = await session.execute(select(Chat))
            for chat in chats.scalars():
                tz = pytz.timezone(chat.timezone)
                target_date = datetime.now(tz) - timedelta(days=1)
                await self._aggregate_for_chat(session, chat, target_date.date())
            await session.commit()

    async def _aggregate_for_chat(self, session: AsyncSession, chat: Chat, target_date: date) -> None:
        settings_row = await self._get_effective_settings(session, chat.id)
        if not settings_row:
            return
        memberships_stmt = select(Membership).where(
            Membership.chat_id == chat.id,
            Membership.role == RoleEnum.OPERATOR,
        )
        memberships = await session.execute(memberships_stmt)
        total = memberships.scalars().all()
        checkins_stmt = select(Checkin.user_id, Checkin.type).where(
            Checkin.chat_id == chat.id,
            Checkin.checkin_date == target_date,
        )
        checkins = await session.execute(checkins_stmt)
        rows = checkins.all()
        morning_cnt = sum(1 for u, t in rows if t == CheckinType.MORNING)
        evening_cnt = sum(1 for u, t in rows if t == CheckinType.EVENING)
        misses = defaultdict(list)
        morning_users = {u for u, t in rows if t == CheckinType.MORNING}
        evening_users = {u for u, t in rows if t == CheckinType.EVENING}
        for membership in total:
            if membership.user_id not in morning_users:
                misses["morning"].append(membership.user_id)
            if membership.user_id not in evening_users:
                misses["evening"].append(membership.user_id)
        stmt = select(DailyStat).where(
            DailyStat.chat_id == chat.id,
            DailyStat.date == target_date,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        payload = {
            "chat_id": chat.id,
            "date": target_date,
            "morning_cnt": morning_cnt,
            "evening_cnt": evening_cnt,
            "total_operators": len(total),
            "misses": dict(misses),
            "created_at": datetime.utcnow(),
        }
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
        else:
            session.add(DailyStat(**payload))

    async def _get_effective_settings(self, session: AsyncSession, chat_id: int) -> Optional[ChatSettings]:
        stmt = select(ChatSettings).where(ChatSettings.chat_id == chat_id)
        result = await session.execute(stmt)
        settings_row = result.scalar_one_or_none()
        if settings_row:
            return settings_row
        stmt = select(ChatSettings).where(ChatSettings.chat_id.is_(None)).limit(1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    def _determine_window(self, settings_row: ChatSettings, now: time) -> Optional[CheckinType]:
        if settings_row.morning_start <= now <= settings_row.morning_end:
            return CheckinType.MORNING
        if settings_row.evening_start <= now <= settings_row.evening_end:
            return CheckinType.EVENING
        return None


async def run_scheduler(notification_service: NotificationService) -> ShiftScheduler:
    scheduler = ShiftScheduler(notification_service)
    scheduler.start()
    return scheduler
