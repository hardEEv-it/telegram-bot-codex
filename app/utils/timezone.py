"""Timezone helper utilities."""
from __future__ import annotations

from datetime import datetime, time
from typing import Tuple

import pytz


def now_in_timezone(tz_name: str) -> datetime:
    tz = pytz.timezone(tz_name)
    return datetime.now(tz)


def parse_time_range(start: time, end: time) -> Tuple[time, time]:
    return start, end
