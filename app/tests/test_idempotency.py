from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.exc import IntegrityError

from ..models import Chat, Checkin, CheckinType, Membership, RoleEnum, User


@pytest.mark.asyncio
async def test_checkin_unique_per_day(session):
    user = User(telegram_id=10, username="idempotent", full_name="User")
    chat = Chat(chat_id=200, title="Shop", timezone="Europe/Sofia")
    session.add_all([user, chat])
    await session.flush()
    membership = Membership(user_id=user.id, chat_id=chat.id, role=RoleEnum.OPERATOR, authorized=True)
    session.add(membership)
    await session.flush()
    payload = dict(
        user_id=user.id,
        chat_id=chat.id,
        type=CheckinType.MORNING,
        photo_file_id="file",
        file_unique_id="uniq",
        created_at=dt.datetime.utcnow(),
        checkin_date=dt.date.today(),
    )
    session.add(Checkin(**payload))
    await session.commit()
    session.add(Checkin(**payload))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()
