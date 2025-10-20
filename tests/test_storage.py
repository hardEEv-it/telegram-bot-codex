import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from storage import Storage, TIME_HORIZON_DEFAULT


@pytest.fixture()
def storage_tmp(tmp_path):
    db_path = tmp_path / "test.db"
    return Storage(str(db_path))


def test_create_and_list(storage_tmp):
    storage = storage_tmp
    wish = storage.create_wish(
        chat_id=1,
        user_id=10,
        user_username="tester",
        user_first_name="Test",
        title="Попробовать новое кафе",
        time_horizon=TIME_HORIZON_DEFAULT,
    )
    wishes, total = storage.list_wishes(chat_id=1)
    assert total == 1
    assert wishes[0].title == "Попробовать новое кафе"

    storage.mark_done(wish.id)
    done_wish = storage.get_wish(wish.id)
    assert done_wish.status == "done"


def test_filters_and_meta(storage_tmp):
    storage = storage_tmp
    storage.create_wish(
        chat_id=2,
        user_id=11,
        user_username=None,
        user_first_name="Ира",
        title="Поход в горы",
        time_horizon="📅 Этот год",
        due_date=date(2024, 12, 31),
        tags="🎁 Подарок",
    )
    storage.create_wish(
        chat_id=2,
        user_id=12,
        user_username=None,
        user_first_name="Макс",
        title="Пикник",
        time_horizon="📆 Этот месяц",
    )

    wishes_month, total_month = storage.list_wishes(chat_id=2, time_horizon="📆 Этот месяц")
    assert total_month == 1
    assert wishes_month[0].title == "Пикник"

    stats = storage.count_stats(2)
    assert stats["total"] == 2
    assert stats["by_horizon"]["📆 Этот месяц"] == 1

    nearest = storage.nearest_with_date(2)
    assert nearest.title == "Поход в горы"

    meta = storage.get_or_init_chat_meta(2)
    assert meta.chat_id == 2
    storage.update_chat_meta(2, timezone="UTC")
    meta2 = storage.get_or_init_chat_meta(2)
    assert meta2.timezone == "UTC"


def test_delete(storage_tmp):
    storage = storage_tmp
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
