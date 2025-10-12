"""Administrative commands."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from ..config import settings
from ..db import async_session_factory
from ..models import Chat, Membership, RoleEnum, User

logger = logging.getLogger(__name__)

router = Router(name="admin")


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "Доступные команды:\n"
        "/help — справка\n"
        "/my — мои роли\n"
        "/report — отчёты\n"
        "/settings — настройки\n"
        "/setrole — управление ролями"
    )


@router.message(Command("health"))
async def health_check(message: Message) -> None:
    await message.answer("OK")


@router.message(Command("lang"))
async def change_language(message: Message) -> None:
    async with async_session_factory() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("Сначала авторизуйтесь")
            return
        current = user.locale or "ru"
        new_locale = "en" if current == "ru" else "ru"
        user.locale = new_locale
        await session.commit()
    await message.answer(f"Язык изменён на {new_locale}")


@router.message(Command("my"))
async def my_roles(message: Message) -> None:
    async with async_session_factory() as session:
        stmt = (
            select(Membership, Chat)
            .join(Chat)
            .join(User, Membership.user_id == User.id)
            .where(User.telegram_id == message.from_user.id)
        )
        result = await session.execute(stmt)
        rows = result.all()
        if not rows:
            await message.answer("Нет ролей")
            return
        lines: List[str] = []
        for membership, chat in rows:
            lines.append(f"Чат {chat.title or chat.chat_id}: роль {membership.role.value}")
        await message.answer("\n".join(lines))


@router.message(Command("setrole"))
async def set_role(message: Message) -> None:
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer("Команда доступна в группе")
        return
    if message.from_user.id != settings.owner_telegram_id:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        if not member.is_chat_admin():
            await message.answer("Недостаточно прав")
            return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Использование: /setrole <user_id|@username> <operator|manager>")
        return
    target_raw, role_raw = parts[1], parts[2].upper()
    if role_raw not in {"OPERATOR", "MANAGER"}:
        await message.answer("Неизвестная роль")
        return
    role = RoleEnum[role_raw]
    target_id = None
    if target_raw.startswith("@"):
        async with async_session_factory() as session:
            stmt = select(User).where(User.username == target_raw[1:])
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user:
                target_id = user.telegram_id
    else:
        try:
            target_id = int(target_raw)
        except ValueError:
            await message.answer("Неверный идентификатор")
            return
    if target_id is None:
        await message.answer("Пользователь не найден")
        return
    async with async_session_factory() as session:
        user_stmt = select(User).where(User.telegram_id == target_id)
        user_res = await session.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не авторизован")
            return
        chat_stmt = select(Chat).where(Chat.chat_id == message.chat.id)
        chat_res = await session.execute(chat_stmt)
        chat = chat_res.scalar_one_or_none()
        if chat is None:
            chat = Chat(chat_id=message.chat.id, title=message.chat.title, timezone=settings.timezone)
            session.add(chat)
            await session.flush()
        membership_stmt = select(Membership).where(Membership.chat_id == chat.id, Membership.user_id == user.id)
        membership_res = await session.execute(membership_stmt)
        membership = membership_res.scalar_one_or_none()
        if membership is None:
            membership = Membership(
                chat_id=chat.id,
                user_id=user.id,
                role=role,
                authorized=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(membership)
        else:
            membership.role = role
            membership.updated_at = datetime.utcnow()
        await session.commit()
    await message.answer("Роль обновлена")
