from datetime import date
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import storage


@pytest.fixture()
def configured_storage(tmp_path):
    db_path = tmp_path / "test.db"
    storage.configure_engine(f"sqlite:///{db_path}")
    return storage


def test_create_and_list(configured_storage):
    storage = configured_storage
    storage.get_or_init_chat_meta(1, "UTC")
    wish = storage.create_wish(
        chat_id=1,
        user_id=10,
        user_username="tester",
        user_first_name="Test",
        title="Попробовать новое кафе",
        time_horizon="📆 Этот месяц",
    )

    wishes, total = storage.list_wishes(chat_id=1)
    assert total == 1
    assert wishes[0].title == "Попробовать новое кафе"

    storage.mark_done(wish.id)
    done_wish = storage.get_wish(wish.id)
    assert done_wish is not None
    assert done_wish.status == "done"


def test_filters_and_meta(configured_storage):
    storage = configured_storage
    storage.get_or_init_chat_meta(2, "Europe/Moscow")

    first = storage.create_wish(
        chat_id=2,
        user_id=11,
        user_username=None,
        user_first_name="Ира",
        title="Поход в горы",
        time_horizon="📅 Этот год",
        due_date=date(2024, 12, 31),
        tags="Подарок",
    )
    storage.create_wish(
        chat_id=2,
        user_id=12,
        user_username=None,
        user_first_name="Макс",
        title="Пикник",
        time_horizon="📆 Этот месяц",
    )

    wishes_month, total_month = storage.list_wishes(
        chat_id=2, status="open", time_horizon="📆 Этот месяц"
    )
    assert total_month == 1
    assert wishes_month[0].title == "Пикник"

    stats = storage.count_stats(2)
    assert stats["total_open"] == 2
    assert stats["by_horizon"]["📆 Этот месяц"] == 1

    nearest = storage.nearest_with_date(2)
    assert nearest is not None
    assert nearest.id == first.id

    random_pick = storage.random_open_wish(2)
    assert random_pick is not None

    meta = storage.get_or_init_chat_meta(2, "UTC")
    assert meta.timezone == "UTC"

    updated = storage.update_wish(first.id, title="Большой поход")
    assert updated is not None
    assert updated.title == "Большой поход"

    chats = storage.list_chats()
    assert any(chat.chat_id == 2 for chat in chats)


def test_delete(configured_storage):
    storage = configured_storage
    storage.get_or_init_chat_meta(3, "UTC")
    wish = storage.create_wish(
        chat_id=3,
        user_id=20,
        user_username=None,
        user_first_name="Лена",
        title="Купить плед",
    )
    ok = storage.delete_wish(wish.id)
    assert ok is True
    wishes, total = storage.list_wishes(chat_id=3)
    assert total == 0
    assert wishes == []
