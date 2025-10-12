"""Group chat interactions."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from ..config import settings
from ..db import async_session_factory
from ..models import Chat
from ..utils.security import encode_deeplink_payload

logger = logging.getLogger(__name__)

router = Router(name="group")
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


@router.my_chat_member()
async def handle_added(event: ChatMemberUpdated) -> None:
    if event.new_chat_member.user.is_bot and event.new_chat_member.user.id == event.bot.id:
        chat_id = event.chat.id
        payload = encode_deeplink_payload(chat_id)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Авторизоваться", url=f"https://t.me/{event.bot.username}?start={payload}")]]
        )
        await event.bot.send_message(
            chat_id,
            "Привет! Чтобы участвовать в отчётах, нужно пройти авторизацию.\n"
            "Нажмите кнопку ниже — откроется личный чат со мной.",
            reply_markup=keyboard,
        )
        async with async_session_factory() as session:
            stmt = select(Chat).where(Chat.chat_id == chat_id)
            result = await session.execute(stmt)
            chat = result.scalar_one_or_none()
            if chat is None:
                session.add(Chat(chat_id=chat_id, title=event.chat.title, timezone=settings.timezone))
            else:
                chat.title = event.chat.title
            await session.commit()


@router.message(Command("link"))
async def manual_link(message: Message) -> None:
    payload = encode_deeplink_payload(message.chat.id)
    url = f"https://t.me/{message.bot.username}?start={payload}"
    await message.reply("Откройте личный чат со мной по ссылке: {url}".format(url=url))
