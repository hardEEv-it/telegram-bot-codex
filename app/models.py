"""Database models for the shift management bot."""
from __future__ import annotations

import enum
from datetime import date, datetime, time
from typing import List, Optional

from sqlalchemy import (JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer,
                        String, Time, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class RoleEnum(str, enum.Enum):
    """Available membership roles."""

    OPERATOR = "OPERATOR"
    MANAGER = "MANAGER"


class AuthorizationMethod(str, enum.Enum):
    """Authorization method enumerator."""

    PHONE = "PHONE"
    CAPTCHA = "CAPTCHA"
    INVITE = "INVITE"


class CheckinType(str, enum.Enum):
    """Shift check-in types."""

    MORNING = "MORNING"
    EVENING = "EVENING"


class User(Base):
    """Telegram user representation."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    phone_last4: Mapped[Optional[str]] = mapped_column(String(4))
    phone_sha256: Mapped[Optional[str]] = mapped_column(String(255))
    phone_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dm_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locale: Mapped[Optional[str]] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    memberships: Mapped[List["Membership"]] = relationship(back_populates="user")
    checkins: Mapped[List["Checkin"]] = relationship(back_populates="user")


class Chat(Base):
    """Telegram chat configuration."""

    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Sofia", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    memberships: Mapped[List["Membership"]] = relationship(back_populates="chat")
    checkins: Mapped[List["Checkin"]] = relationship(back_populates="chat")
    settings: Mapped[List["ChatSettings"]] = relationship(back_populates="chat")


class Membership(Base):
    """Mapping between users and chats with role."""

    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), nullable=False, default=RoleEnum.OPERATOR)
    authorized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    authorized_via: Mapped[Optional[AuthorizationMethod]] = mapped_column(Enum(AuthorizationMethod))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="memberships")
    chat: Mapped["Chat"] = relationship(back_populates="memberships")

    __table_args__ = (UniqueConstraint("user_id", "chat_id", name="uq_membership_user_chat"),)


class Checkin(Base):
    """Shift checkins."""

    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[CheckinType] = mapped_column(Enum(CheckinType), nullable=False)
    photo_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    file_unique_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    checkin_date: Mapped[date] = mapped_column(Date, nullable=False)

    user: Mapped["User"] = relationship(back_populates="checkins")
    chat: Mapped["Chat"] = relationship(back_populates="checkins")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "chat_id",
            "type",
            "checkin_date",
            name="uq_checkins_user_chat_type_date",
        ),
    )


class ChatSettings(Base):
    """Per-chat settings."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    morning_start: Mapped[time] = mapped_column(Time, nullable=False)
    morning_end: Mapped[time] = mapped_column(Time, nullable=False)
    evening_start: Mapped[time] = mapped_column(Time, nullable=False)
    evening_end: Mapped[time] = mapped_column(Time, nullable=False)
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_weekends: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)

    chat: Mapped[Optional["Chat"]] = relationship(back_populates="settings")


class DailyStat(Base):
    """Aggregated daily statistics."""

    __tablename__ = "daily_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    morning_cnt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evening_cnt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_operators: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    misses: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    chat: Mapped["Chat"] = relationship()
