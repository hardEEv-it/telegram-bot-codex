from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, create_engine, func, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

__all__ = [
    "ChatMeta",
    "Wish",
    "configure_engine",
    "get_or_init_chat_meta",
    "create_wish",
    "list_wishes",
    "random_open_wish",
    "nearest_with_date",
    "count_stats",
    "get_wish",
    "update_wish",
    "mark_done",
    "delete_wish",
    "list_chats",
]


DEFAULT_DATABASE_URL = "sqlite:////app/data/wishes.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

_engine: Optional[Engine] = None
_Session: Optional[sessionmaker[Session]] = None


class Base(DeclarativeBase):
    pass


class ChatMeta(Base):
    __tablename__ = "chats"

    chat_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    last_added_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class Wish(Base):
    __tablename__ = "wishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user_first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    photo_file_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    price_amount: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    time_horizon: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


def configure_engine(database_url: Optional[str] = None) -> None:
    """Configure SQLAlchemy engine and session factory."""

    global DATABASE_URL, _engine, _Session

    target_url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    url = make_url(target_url)

    if url.get_backend_name() == "sqlite":
        os.makedirs("/app/data", exist_ok=True)
        if url.database:
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        target_url,
        connect_args={"check_same_thread": False} if url.get_backend_name() == "sqlite" else {},
        pool_pre_ping=True,
    )

    if _engine is not None:
        _engine.dispose()

    Base.metadata.create_all(engine)

    DATABASE_URL = target_url
    _engine = engine
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)


configure_engine(DATABASE_URL)


@contextmanager
def session_scope() -> Iterator[Session]:
    if _Session is None:
        raise RuntimeError("Database engine is not configured.")

    session: Session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_or_init_chat_meta(chat_id: int, timezone: str) -> ChatMeta:
    with session_scope() as session:
        meta = session.get(ChatMeta, chat_id)
        if meta:
            if timezone and meta.timezone != timezone:
                meta.timezone = timezone
            session.flush()
            session.refresh(meta)
            return meta
        meta = ChatMeta(chat_id=chat_id, timezone=timezone)
        session.add(meta)
        session.flush()
        session.refresh(meta)
        return meta


def create_wish(
    *,
    chat_id: int,
    user_id: Optional[int],
    user_first_name: Optional[str],
    user_username: Optional[str],
    title: str,
    photo_file_id: Optional[str] = None,
    price_flag: Optional[bool] = None,
    price_amount: Optional[str] = None,
    time_horizon: Optional[str] = None,
    due_date: Optional[date] = None,
    tags: Optional[str] = None,
) -> Wish:
    now = datetime.utcnow()
    with session_scope() as session:
        wish = Wish(
            chat_id=chat_id,
            user_id=user_id,
            user_first_name=user_first_name,
            user_username=user_username,
            title=title,
            photo_file_id=photo_file_id,
            price_flag=bool(price_flag) if price_flag is not None else False,
            price_amount=price_amount,
            time_horizon=time_horizon,
            due_date=due_date,
            tags=tags,
            status="open",
            created_at=now,
        )
        session.add(wish)

        chat = session.get(ChatMeta, chat_id)
        if chat:
            chat.last_added_at = now

        session.flush()
        session.refresh(wish)
        return wish


def list_wishes(
    chat_id: int,
    status: Optional[str] = None,
    time_horizon: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
) -> Tuple[List[Wish], int]:
    limit = max(1, int(limit or 1))
    offset = max(0, int(offset or 0))

    with session_scope() as session:
        filters = [Wish.chat_id == chat_id]
        if status:
            filters.append(Wish.status == status)
        if time_horizon:
            filters.append(Wish.time_horizon == time_horizon)

        total_stmt = select(func.count(Wish.id)).where(*filters)
        total = session.execute(total_stmt).scalar_one()

        page_stmt = (
            select(Wish)
            .where(*filters)
            .order_by(Wish.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        wishes = session.execute(page_stmt).scalars().all()
        return wishes, total


def random_open_wish(chat_id: int) -> Optional[Wish]:
    with session_scope() as session:
        stmt = (
            select(Wish)
            .where(Wish.chat_id == chat_id, Wish.status == "open")
            .order_by(func.random())
            .limit(1)
        )
        return session.execute(stmt).scalar_one_or_none()


def nearest_with_date(chat_id: int) -> Optional[Wish]:
    with session_scope() as session:
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


def count_stats(chat_id: int) -> Dict[str, object]:
    with session_scope() as session:
        status_rows = session.execute(
            select(Wish.status, func.count())
            .where(Wish.chat_id == chat_id)
            .group_by(Wish.status)
        ).all()
        status_counts = {row[0]: row[1] for row in status_rows}

        horizon_rows = session.execute(
            select(Wish.time_horizon, func.count())
            .where(Wish.chat_id == chat_id, Wish.status == "open")
            .group_by(Wish.time_horizon)
        ).all()
        by_horizon = {row[0] or "Без срока": row[1] for row in horizon_rows}

        return {
            "total_open": status_counts.get("open", 0),
            "total_done": status_counts.get("done", 0),
            "by_horizon": by_horizon,
        }


def get_wish(wish_id: int) -> Optional[Wish]:
    with session_scope() as session:
        return session.get(Wish, wish_id)


def update_wish(wish_id: int, **fields) -> Optional[Wish]:
    with session_scope() as session:
        wish = session.get(Wish, wish_id)
        if not wish:
            return None
        for key, value in fields.items():
            if hasattr(wish, key):
                setattr(wish, key, value)
        session.flush()
        session.refresh(wish)
        return wish


def mark_done(wish_id: int) -> Optional[Wish]:
    now = datetime.utcnow()
    with session_scope() as session:
        wish = session.get(Wish, wish_id)
        if not wish:
            return None
        if wish.status != "done":
            wish.status = "done"
            wish.done_at = now
            session.flush()
        session.refresh(wish)
        return wish


def delete_wish(wish_id: int) -> bool:
    with session_scope() as session:
        wish = session.get(Wish, wish_id)
        if not wish:
            return False
        session.delete(wish)
        return True


def list_chats() -> List[ChatMeta]:
    with session_scope() as session:
        stmt = select(ChatMeta)
        return list(session.execute(stmt).scalars())
