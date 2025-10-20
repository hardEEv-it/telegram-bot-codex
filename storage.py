from __future__ import annotations

import random
from contextlib import contextmanager
from datetime import UTC, datetime, date
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


TIME_HORIZON_DEFAULT = "⏳ Когда-нибудь"
TIME_HORIZONS = [
    "⚡ Прямо сейчас",
    "📆 Этот месяц",
    "📅 Этот год",
    TIME_HORIZON_DEFAULT,
    "🗓 Точная дата",
]


class Base(DeclarativeBase):
    pass


class Wish(Base):
    __tablename__ = "wishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    user_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    photo_file_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price_flag: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    time_horizon: Mapped[str] = mapped_column(String(32), nullable=False, default=TIME_HORIZON_DEFAULT, index=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ChatMeta(Base):
    __tablename__ = "chat_meta"

    chat_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    next_ping_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Sofia")


class Storage:
    def __init__(self, db_path: str = "wishes.db") -> None:
        self.engine = create_engine(f"sqlite:///{db_path}", future=True, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False, class_=Session)

    @contextmanager
    def session_scope(self) -> Iterable[Session]:
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # Wishes CRUD
    def create_wish(
        self,
        *,
        chat_id: int,
        user_id: int,
        title: str,
        user_username: Optional[str],
        user_first_name: Optional[str],
        photo_file_id: Optional[str] = None,
        price_flag: bool = False,
        price_amount: Optional[float] = None,
        time_horizon: str = TIME_HORIZON_DEFAULT,
        due_date: Optional[date] = None,
        tags: Optional[str] = None,
    ) -> Wish:
        now = datetime.now(UTC)
        with self.session_scope() as session:
            wish = Wish(
                chat_id=chat_id,
                user_id=user_id,
                user_username=user_username,
                user_first_name=user_first_name,
                title=title,
                photo_file_id=photo_file_id,
                price_flag=1 if price_flag else 0,
                price_amount=price_amount,
                time_horizon=time_horizon,
                due_date=due_date,
                tags=tags,
                status="open",
                created_at=now,
            )
            session.add(wish)
            session.flush()
            session.refresh(wish)
            return wish

    def get_wish(self, wish_id: int) -> Optional[Wish]:
        with self.session_scope() as session:
            return session.get(Wish, wish_id)

    def update_wish(self, wish_id: int, **fields) -> Optional[Wish]:
        with self.session_scope() as session:
            wish = session.get(Wish, wish_id)
            if not wish:
                return None
            for key, value in fields.items():
                if hasattr(wish, key):
                    setattr(wish, key, value)
            session.flush()
            session.refresh(wish)
            return wish

    def mark_done(self, wish_id: int) -> Optional[Wish]:
        now = datetime.now(UTC)
        with self.session_scope() as session:
            wish = session.get(Wish, wish_id)
            if not wish:
                return None
            if wish.status == "done":
                return wish
            wish.status = "done"
            wish.done_at = now
            session.flush()
            session.refresh(wish)
            return wish

    def delete_wish(self, wish_id: int) -> bool:
        with self.session_scope() as session:
            wish = session.get(Wish, wish_id)
            if not wish:
                return False
            session.delete(wish)
            return True

    def list_wishes(
        self,
        *,
        chat_id: int,
        status: Optional[str] = None,
        time_horizon: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Tuple[List[Wish], int]:
        with self.session_scope() as session:
            base_stmt = select(Wish).where(Wish.chat_id == chat_id)
            if status:
                base_stmt = base_stmt.where(Wish.status == status)
            if time_horizon:
                base_stmt = base_stmt.where(Wish.time_horizon == time_horizon)

            count_stmt = select(func.count()).select_from(base_stmt.subquery())
            total = session.execute(count_stmt).scalar_one()

            stmt = base_stmt.order_by(Wish.created_at.desc()).limit(limit).offset(offset)
            wishes = list(session.execute(stmt).scalars())
            return wishes, total

    def random_open_wish(self, chat_id: int) -> Optional[Wish]:
        with self.session_scope() as session:
            stmt = select(Wish).where(Wish.chat_id == chat_id, Wish.status == "open")
            wishes = list(session.execute(stmt).scalars())
            if not wishes:
                return None
            return random.choice(wishes)

    def nearest_with_date(self, chat_id: int) -> Optional[Wish]:
        with self.session_scope() as session:
            stmt = (
                select(Wish)
                .where(
                    Wish.chat_id == chat_id,
                    Wish.status == "open",
                    Wish.due_date.is_not(None),
                )
                .order_by(Wish.due_date.asc())
                .limit(1)
            )
            return session.execute(stmt).scalar_one_or_none()

    def count_stats(self, chat_id: int) -> dict:
        with self.session_scope() as session:
            result = session.execute(
                select(Wish.time_horizon, func.count())
                .where(Wish.chat_id == chat_id, Wish.status == "open")
                .group_by(Wish.time_horizon)
            )
            by_horizon = {row[0]: row[1] for row in result}
            total = sum(by_horizon.values())
            return {"total": total, "by_horizon": by_horizon}

    # Chat meta
    def get_or_init_chat_meta(self, chat_id: int, default_timezone: str = "Europe/Sofia") -> ChatMeta:
        with self.session_scope() as session:
            meta = session.get(ChatMeta, chat_id)
            if meta:
                return meta
            meta = ChatMeta(chat_id=chat_id, timezone=default_timezone, next_ping_at=None)
            session.add(meta)
            session.flush()
            session.refresh(meta)
            return meta

    def update_chat_meta(self, chat_id: int, **fields) -> Optional[ChatMeta]:
        with self.session_scope() as session:
            meta = session.get(ChatMeta, chat_id)
            if not meta:
                return None
            for key, value in fields.items():
                if hasattr(meta, key):
                    setattr(meta, key, value)
            session.flush()
            session.refresh(meta)
            return meta

    def due_chat_metas(self, now: datetime) -> List[ChatMeta]:
        with self.session_scope() as session:
            stmt = select(ChatMeta).where(ChatMeta.next_ping_at.is_not(None), ChatMeta.next_ping_at <= now)
            return list(session.execute(stmt).scalars())


__all__ = [
    "Storage",
    "Wish",
    "ChatMeta",
    "TIME_HORIZONS",
    "TIME_HORIZON_DEFAULT",
]
