"""Seed database with demo data."""
from __future__ import annotations

import asyncio
from datetime import datetime

from ..db import async_session_factory
from ..models import Chat, ChatSettings, RoleEnum, User, Membership


async def seed() -> None:
    async with async_session_factory() as session:
        user = User(telegram_id=1, username="owner", full_name="Owner", created_at=datetime.utcnow())
        chat = Chat(chat_id=12345, title="Demo Chat")
        session.add_all([user, chat])
        await session.flush()
        membership = Membership(user_id=user.id, chat_id=chat.id, role=RoleEnum.MANAGER, authorized=True)
        session.add(membership)
        await session.commit()
        print("Seed completed")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
