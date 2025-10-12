"""Chat settings management."""
from __future__ import annotations

from datetime import time
from typing import Optional

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from ..config import settings
from ..db import async_session_factory
from ..models import Chat, ChatSettings, Membership, RoleEnum, User

router = Router(name="settings")


@router.message(Command("settings"))
async def show_settings(message: Message) -> None:
    async with async_session_factory() as session:
        stmt = (
            select(Membership, Chat, ChatSettings)
            .join(Chat)
            .outerjoin(ChatSettings, ChatSettings.chat_id == Chat.id)
            .join(User, Membership.user_id == User.id)
            .where(User.telegram_id == message.from_user.id)
        )
        res = await session.execute(stmt)
        row = res.first()
        if not row:
            await message.answer("Нет доступа")
            return
        membership, chat, chat_settings = row
        if membership.role != RoleEnum.MANAGER and message.from_user.id != settings.owner_telegram_id:
            await message.answer("Только управляющий может изменять настройки")
            return
        chat_settings = chat_settings or await _ensure_chat_settings(session, chat.id, chat.timezone)
        text = (
            f"Настройки чата {chat.title or chat.chat_id}:\n"
            f"Утро: {chat_settings.morning_start}-{chat_settings.morning_end}\n"
            f"Вечер: {chat_settings.evening_start}-{chat_settings.evening_end}\n"
            f"Таймзона: {chat_settings.timezone}\n"
            f"Алерты: {'Вкл' if chat_settings.alerts_enabled else 'Выкл'}\n"
            f"Выходные: {'Учитывать' if chat_settings.include_weekends else 'Игнорировать'}"
        )
        await message.answer(text, reply_markup=_settings_keyboard(chat_settings))


@router.callback_query(F.data.startswith("settings:toggle"))
async def toggle_setting(callback: CallbackQuery) -> None:
    _, _, field = callback.data.split(":")
    async with async_session_factory() as session:
        stmt = (
            select(Membership, ChatSettings)
            .join(ChatSettings, ChatSettings.chat_id == Membership.chat_id)
            .join(User, Membership.user_id == User.id)
            .where(User.telegram_id == callback.from_user.id)
        )
        res = await session.execute(stmt)
        row = res.first()
        if not row:
            await callback.answer("Нет доступа", show_alert=True)
            return
        membership, chat_settings = row
        if membership.role != RoleEnum.MANAGER and callback.from_user.id != settings.owner_telegram_id:
            await callback.answer("Недостаточно прав", show_alert=True)
            return
        if field == "alerts":
            chat_settings.alerts_enabled = not chat_settings.alerts_enabled
        elif field == "weekend":
            chat_settings.include_weekends = not chat_settings.include_weekends
        await session.commit()
        await callback.message.edit_reply_markup(reply_markup=_settings_keyboard(chat_settings))
    await callback.answer("Обновлено")


def _settings_keyboard(settings_row: ChatSettings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Алерты: {'Вкл' if settings_row.alerts_enabled else 'Выкл'}", callback_data="settings:toggle:alerts")],
            [InlineKeyboardButton(text=f"Выходные: {'Да' if settings_row.include_weekends else 'Нет'}", callback_data="settings:toggle:weekend")],
        ]
    )


async def _ensure_chat_settings(session, chat_id: int, timezone: str) -> ChatSettings:
    stmt = select(ChatSettings).where(ChatSettings.chat_id == chat_id)
    res = await session.execute(stmt)
    settings_row = res.scalar_one_or_none()
    if settings_row:
        return settings_row
    settings_row = ChatSettings(
        chat_id=chat_id,
        morning_start=time(6, 0),
        morning_end=time(11, 0),
        evening_start=time(16, 0),
        evening_end=time(23, 0),
        alerts_enabled=True,
        include_weekends=True,
        timezone=timezone,
    )
    session.add(settings_row)
    await session.commit()
    return settings_row
