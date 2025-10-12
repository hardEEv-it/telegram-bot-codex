from __future__ import annotations

import datetime as dt

import pytest

from sqlalchemy import select

from ..models import Chat, Checkin, CheckinType, DailyStat, Membership, RoleEnum, User
from ..scheduler import ShiftScheduler
from ..services.notifications import NotificationService


class DummyNotification(NotificationService):
    def __init__(self):  # type: ignore[super-init-not-called]
        self.messages = []

    async def send_reminder(self, chat, window, memberships):  # type: ignore[override]
        self.messages.append((chat.chat_id, window, len(memberships)))


@pytest.mark.asyncio
async def test_aggregate_daily_stats(session):
    notification = DummyNotification()
    scheduler = ShiftScheduler(notification)
    user = User(telegram_id=1, username="user", full_name="Test")
    chat = Chat(chat_id=100, title="Team", timezone="Europe/Sofia")
    session.add_all([user, chat])
    await session.flush()
    membership = Membership(user_id=user.id, chat_id=chat.id, role=RoleEnum.OPERATOR, authorized=True)
    session.add(membership)
    await session.flush()
    today = dt.date.today()
    session.add(
        Checkin(
            user_id=user.id,
            chat_id=chat.id,
            type=CheckinType.MORNING,
            photo_file_id="file",
            file_unique_id="unique",
            created_at=dt.datetime.utcnow(),
            checkin_date=today,
        )
    )
    await session.commit()
    await scheduler._aggregate_for_chat(session, chat, today)
    await session.commit()
    result = await session.execute(
        select(DailyStat).where(DailyStat.chat_id == chat.id, DailyStat.date == today)
    )
    stat = result.scalar_one()
    assert stat.morning_cnt == 1
    assert stat.evening_cnt == 0
    assert stat.total_operators == 1
