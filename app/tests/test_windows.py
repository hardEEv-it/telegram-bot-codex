from __future__ import annotations

import datetime as dt

from ..models import ChatSettings, CheckinType
from ..routers.checkins import _is_within_window


def test_window_detection_defaults():
    settings = None
    now = dt.time(6, 30)
    assert _is_within_window(settings, now, CheckinType.MORNING)
    assert not _is_within_window(settings, dt.time(5, 59), CheckinType.MORNING)
    assert _is_within_window(settings, dt.time(17, 0), CheckinType.EVENING)


def test_window_detection_custom():
    settings = ChatSettings(
        chat_id=1,
        morning_start=dt.time(7, 0),
        morning_end=dt.time(9, 0),
        evening_start=dt.time(18, 0),
        evening_end=dt.time(21, 0),
        alerts_enabled=True,
        include_weekends=False,
        timezone="Europe/Sofia",
    )
    assert _is_within_window(settings, dt.time(7, 30), CheckinType.MORNING)
    assert not _is_within_window(settings, dt.time(6, 59), CheckinType.MORNING)
