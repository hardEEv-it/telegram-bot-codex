"""Notification service consolidating bot messaging logic."""
from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from ..models import CheckinType, Chat, Membership

logger = logging.getLogger(__name__)

RATE_LIMIT_PER_SECOND = 25


class NotificationService:
    """Fan-out notifications with rate limiting and retries."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send_reminder(self, chat: Chat, window: CheckinType, memberships: Sequence[Membership]) -> None:
        usernames = [self._format_member(m) for m in memberships]
        text = (
            "⚠️ В чате {title} еще не отметились за {window}: {users}".format(
                title=chat.title or chat.chat_id,
                window="утро" if window == CheckinType.MORNING else "вечер",
                users=", ".join(usernames),
            )
        )
        await self._send_message(chat.chat_id, text)

    async def send_daily_report(self, chat_id: int, text: str, attachments: Sequence[dict]) -> None:
        await self._send_message(chat_id, text, attachments=attachments)

    async def _send_message(self, chat_id: int, text: str, attachments: Sequence[dict] | None = None) -> None:
        try:
            await self.bot.send_message(chat_id=chat_id, text=text)
            if attachments:
                for attach in attachments:
                    kind = attach.get("type")
                    if kind == "photo":
                        await self.bot.send_photo(chat_id, attach["file"], caption=attach.get("caption"))
                    elif kind == "document":
                        await self.bot.send_document(chat_id, attach["file"], caption=attach.get("caption"))
        except TelegramRetryAfter as exc:
            delay = exc.retry_after + 1
            logger.warning("Rate limited, retrying after %s seconds", delay)
            await asyncio.sleep(delay)
            await self._send_message(chat_id, text, attachments=attachments)
        except TelegramForbiddenError:
            logger.info("Bot blocked by chat %s", chat_id)
        except Exception:  # pragma: no cover - fallback
            logger.exception("Failed to send message to %s", chat_id)

    def _format_member(self, membership: Membership) -> str:
        username = membership.user.username
        return f"@{username}" if username else membership.user.full_name or str(membership.user.telegram_id)
