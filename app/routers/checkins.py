"""Check-in handlers."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import pytz
from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from ..config import settings
from ..db import async_session_factory
from ..models import Chat, ChatSettings, Checkin, CheckinType, Membership, RoleEnum, User

router = Router(name="checkins")
router.message.filter(F.chat.type == ChatType.PRIVATE)


class CheckinState(StatesGroup):
    waiting_for_photo = State()
    waiting_for_confirmation = State()


@router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext) -> None:
    photos = message.photo
    if not photos:
        return
    best = photos[-1]
    now = dt.datetime.utcnow()
    await state.update_data(
        photo_file_id=best.file_id,
        file_unique_id=best.file_unique_id,
        received_at=now.isoformat(),
    )
    await state.set_state(CheckinState.waiting_for_confirmation)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я пришёл на работу", callback_data="checkin:confirm:MORNING")],
            [InlineKeyboardButton(text="Смену завершил", callback_data="checkin:confirm:EVENING")],
        ]
    )
    await message.answer("Выберите отметку", reply_markup=keyboard)


@router.callback_query(F.data.startswith("checkin:confirm"))
async def confirm_checkin(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data:
        await callback.answer("Отправьте актуальное фото", show_alert=True)
        return
    received_at = dt.datetime.fromisoformat(data["received_at"])
    if (dt.datetime.utcnow() - received_at) > dt.timedelta(minutes=2):
        await state.clear()
        await callback.answer("Фото устарело, отправьте новое", show_alert=True)
        return
    async with async_session_factory() as session:
        memberships_stmt = (
            select(Membership)
            .join(User)
            .where(
                User.telegram_id == callback.from_user.id,
                Membership.authorized.is_(True),
            )
        )
        result = await session.execute(memberships_stmt)
        memberships = result.scalars().all()
        if not memberships:
            await callback.answer("Сначала пройдите авторизацию", show_alert=True)
            return
        membership = memberships[0]
        chat = await session.get(Chat, membership.chat_id)
        settings_stmt = select(ChatSettings).where(ChatSettings.chat_id == chat.id)
        settings_result = await session.execute(settings_stmt)
        chat_settings = settings_result.scalar_one_or_none()
        tz = pytz.timezone(chat_settings.timezone if chat_settings else chat.timezone)
        now_dt = dt.datetime.now(tz)
        if chat_settings and not chat_settings.include_weekends and now_dt.weekday() >= 5:
            await callback.answer("Сегодня отметки не требуются", show_alert=True)
            return
        now_local = now_dt.timetz()
        _, _, _, type_name = callback.data.split(":")
        checkin_type = CheckinType[type_name]
        if not _is_within_window(chat_settings, now_local, checkin_type):
            await callback.answer("Сейчас отметка недоступна", show_alert=True)
            return
        today_local = now_dt.date()
        exists_stmt = select(Checkin).where(
            Checkin.user_id == membership.user_id,
            Checkin.chat_id == chat.id,
            Checkin.type == checkin_type,
            Checkin.checkin_date == today_local,
        )
        exists_result = await session.execute(exists_stmt)
        if exists_result.scalar_one_or_none():
            await callback.answer("✅ Отметка уже зафиксирована", show_alert=True)
            return
        session.add(
            Checkin(
                user_id=membership.user_id,
                chat_id=chat.id,
                type=checkin_type,
                photo_file_id=data["photo_file_id"],
                file_unique_id=data["file_unique_id"],
                created_at=dt.datetime.utcnow(),
                checkin_date=today_local,
            )
        )
        await session.commit()
    await state.clear()
    await callback.message.answer("✅ Отметка сохранена")
    await callback.answer()


def _is_within_window(settings_row: Optional[ChatSettings], now: dt.time, checkin_type: CheckinType) -> bool:
    if settings_row is None:
        morning_start = dt.time(hour=6)
        morning_end = dt.time(hour=11)
        evening_start = dt.time(hour=16)
        evening_end = dt.time(hour=23)
    else:
        morning_start = settings_row.morning_start
        morning_end = settings_row.morning_end
        evening_start = settings_row.evening_start
        evening_end = settings_row.evening_end
    if checkin_type == CheckinType.MORNING:
        return morning_start <= now <= morning_end
    return evening_start <= now <= evening_end
