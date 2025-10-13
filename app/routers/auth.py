"""Authorization flows in private chat."""
from __future__ import annotations

import random
from datetime import datetime
from typing import Optional

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, Message, ReplyKeyboardMarkup)
from sqlalchemy import select

from ..config import settings
from ..db import async_session_factory
from ..models import AuthorizationMethod, Chat, Membership, RoleEnum, User
from ..utils.security import decode_deeplink_payload, hash_phone_number

router = Router(name="auth")
router.message.filter(F.chat.type == ChatType.PRIVATE)


class AuthorizationState(StatesGroup):
    """FSM states for authorization."""

    waiting_for_method = State()
    waiting_for_captcha = State()
    waiting_for_invite = State()
    waiting_for_contact = State()


CAPTCHA_VARIANTS = [
    (3, 4),
    (5, 7),
    (2, 9),
]


def _build_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📞 Поделиться телефоном", callback_data="auth:phone")],
        [InlineKeyboardButton(text="🧮 Капча", callback_data="auth:captcha")],
        [InlineKeyboardButton(text="🔑 Код приглашения", callback_data="auth:invite")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(CommandStart())
async def start_authorization(message: Message, state: FSMContext) -> None:
    payload = message.text.split(maxsplit=1)[-1] if message.text else ""
    chat_id: Optional[int] = None
    if payload and payload != "/start":
        try:
            chat_id = decode_deeplink_payload(payload)
        except Exception:
            chat_id = None
    await state.update_data(target_chat_id=chat_id)
    await state.set_state(AuthorizationState.waiting_for_method)
    await message.answer(
        "Привет! Выберите способ авторизации.",
        reply_markup=_build_main_keyboard(),
    )


@router.callback_query(F.data == "auth:phone")
async def request_phone(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AuthorizationState.waiting_for_contact)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Поделиться телефоном", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await callback.message.answer("Отправьте номер телефона", reply_markup=keyboard)
    await callback.answer()


@router.message(AuthorizationState.waiting_for_contact, F.contact)
async def receive_contact(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id = data.get("target_chat_id")
    if not chat_id:
        await message.answer("Не удалось определить чат. Используйте /link в группе.")
        await state.clear()
        return
    phone = message.contact.phone_number
    sha, last4 = hash_phone_number(phone)
    async with async_session_factory() as session:
        await _persist_authorization(
            session,
            user=message.from_user,
            chat_id=chat_id,
            method=AuthorizationMethod.PHONE,
            phone_sha=sha,
            phone_last4=last4,
        )
    await state.clear()
    await message.answer("✅ Авторизация завершена", reply_markup=None)


@router.callback_query(F.data == "auth:captcha")
async def start_captcha(callback: CallbackQuery, state: FSMContext) -> None:
    a, b = random.choice(CAPTCHA_VARIANTS)
    result = a + b
    variants = [result, result + 1, result - 1]
    random.shuffle(variants)
    buttons = [
        InlineKeyboardButton(text=str(value), callback_data=f"auth:capture:{value}:{result}")
        for value in variants
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=[buttons])
    await state.set_state(AuthorizationState.waiting_for_captcha)
    await state.update_data(captcha_answer=result)
    await callback.message.answer(f"Сколько будет {a}+{b}?", reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("auth:capture"))
async def validate_captcha(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id = data.get("target_chat_id")
    if not chat_id:
        await callback.answer("Неизвестный чат", show_alert=True)
        return
    _, _, value, expected = callback.data.split(":")
    if value != expected:
        await callback.answer("Неверно", show_alert=True)
        return
    async with async_session_factory() as session:
        await _persist_authorization(
            session,
            user=callback.from_user,
            chat_id=chat_id,
            method=AuthorizationMethod.CAPTCHA,
        )
    await state.clear()
    await callback.message.answer("✅ Авторизация через капчу выполнена")
    await callback.answer()


@router.callback_query(F.data == "auth:invite")
async def request_invite(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AuthorizationState.waiting_for_invite)
    await callback.message.answer("Введите код приглашения")
    await callback.answer()


@router.message(AuthorizationState.waiting_for_invite)
async def validate_invite(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    chat_id = data.get("target_chat_id")
    if not chat_id:
        await message.answer("Не удалось определить чат")
        await state.clear()
        return
    code = message.text.strip()
    if code != "123456":  # Placeholder, should check DB stored invites
        await message.answer("Неверный код, попробуйте снова")
        return
    async with async_session_factory() as session:
        await _persist_authorization(
            session,
            user=message.from_user,
            chat_id=chat_id,
            method=AuthorizationMethod.INVITE,
        )
    await state.clear()
    await message.answer("✅ Авторизация выполнена")


async def _persist_authorization(
    session: AsyncSession,
    user,
    chat_id: int,
    method: AuthorizationMethod,
    phone_sha: Optional[str] = None,
    phone_last4: Optional[str] = None,
) -> None:
    stmt = select(User).where(User.telegram_id == user.id)
    result = await session.execute(stmt)
    user_db = result.scalar_one_or_none()
    now = datetime.utcnow()
    if user_db is None:
        user_db = User(
            telegram_id=user.id,
            username=user.username,
            full_name=user.full_name,
            phone_sha256=phone_sha,
            phone_last4=phone_last4,
            phone_verified_at=now if phone_sha else None,
            created_at=now,
        )
        session.add(user_db)
        await session.flush()
    else:
        user_db.username = user.username
        user_db.full_name = user.full_name
        if phone_sha:
            user_db.phone_sha256 = phone_sha
            user_db.phone_last4 = phone_last4
            user_db.phone_verified_at = now
    chat_stmt = select(Chat).where(Chat.chat_id == chat_id)
    chat_result = await session.execute(chat_stmt)
    chat_db = chat_result.scalar_one_or_none()
    if chat_db is None:
        chat_db = Chat(chat_id=chat_id, timezone=settings.timezone)
        session.add(chat_db)
        await session.flush()
    membership_stmt = select(Membership).where(
        Membership.chat_id == chat_db.id,
        Membership.user_id == user_db.id,
    )
    membership_result = await session.execute(membership_stmt)
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        membership = Membership(
            chat_id=chat_db.id,
            user_id=user_db.id,
            role=RoleEnum.OPERATOR,
            authorized=True,
            authorized_via=method,
            created_at=now,
            updated_at=now,
        )
        session.add(membership)
    else:
        membership.authorized = True
        membership.authorized_via = method
        membership.updated_at = now

    await session.commit()
