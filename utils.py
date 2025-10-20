from __future__ import annotations

import html
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

import pytz

from storage import TIME_HORIZON_DEFAULT, TIME_HORIZONS, Wish

TAG_OPTIONS = [
    "🎁 Подарок",
    "💑 Для двоих",
    "🧸 Маленькая хотелка",
    "🚀 Большая мечта",
    "🌿 На природе",
    "🏠 Домашнее",
    "🍽 Еда",
    "🎬 Развлечения",
]

TIME_HORIZON_LABELS = {key: key for key in TIME_HORIZONS}


@dataclass
class SummaryData:
    total: int
    by_horizon: Dict[str, int]
    nearest: Optional[Wish]
    random_wish: Optional[Wish]


def escape(text: Optional[str]) -> str:
    if not text:
        return ""
    return html.escape(text)


def format_price(wish: Wish) -> str:
    if not wish.price_flag:
        return "—"
    if wish.price_amount is None:
        return "есть"
    return f"есть (≈ {wish.price_amount:g})"


def format_tags(tags: Optional[str]) -> str:
    if not tags:
        return "—"
    return ", ".join(part.strip() for part in tags.split(",") if part.strip()) or "—"


def format_status(wish: Wish) -> str:
    return "done" if wish.status == "done" else "open"


def format_user(wish: Wish) -> str:
    if wish.user_username:
        return f"@{escape(wish.user_username)}"
    if wish.user_first_name:
        return escape(wish.user_first_name)
    return "кто-то из вас"


def format_time_horizon(wish: Wish) -> str:
    label = TIME_HORIZON_LABELS.get(wish.time_horizon, TIME_HORIZON_DEFAULT)
    if wish.time_horizon == "🗓 Точная дата" and wish.due_date:
        return f"{label} — {wish.due_date.isoformat()}"
    return label


def format_wish_caption(wish: Wish) -> str:
    parts = [
        f"<b>Желание:</b> {escape(wish.title)}",
        f"<b>Цена:</b> {escape(format_price(wish))}",
        f"<b>Когда:</b> {escape(format_time_horizon(wish))}",
        f"<b>Теги:</b> {escape(format_tags(wish.tags))}",
        f"<b>Статус:</b> {escape(format_status(wish))}",
        f"<b>Добавил(а):</b> {format_user(wish)}",
    ]
    return "\n".join(parts)


def parse_price(text: str) -> Optional[float]:
    cleaned = text.strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError as exc:
        raise ValueError("Не могу понять сумму. Напишите просто число, например 2500") from exc


def parse_due_date(text: str) -> date:
    cleaned = text.strip()
    try:
        year, month, day = map(int, cleaned.split("-"))
        return date(year, month, day)
    except Exception as exc:
        raise ValueError("Дата должна быть в формате YYYY-MM-DD") from exc


def serialize_tags(selected: Iterable[str]) -> str:
    return ",".join(sorted(set(selected)))


def toggle_tag(current: Optional[str], tag: str) -> str:
    selected = set(part.strip() for part in (current.split(",") if current else []) if part.strip())
    if tag in selected:
        selected.remove(tag)
    else:
        selected.add(tag)
    return serialize_tags(selected)


def compute_next_ping(now_utc: datetime, tz_name: str, days: int = 14) -> datetime:
    tz = pytz.timezone(tz_name)
    local = now_utc.astimezone(tz) + timedelta(days=days)
    local = local.replace(hour=10, minute=0, second=0, microsecond=0)
    return local.astimezone(pytz.utc)


def ensure_initial_ping(now_utc: datetime, tz_name: str) -> datetime:
    return compute_next_ping(now_utc, tz_name, days=14)


MICRO_TIPS = [
    "обсудить 10 минут сегодня",
    "выбрать одно желание и сделать микро-шаг",
]


def pick_micro_tip(wish: Optional[Wish]) -> str:
    if not wish:
        return "обсудить 10 минут сегодня"
    if wish.price_flag:
        return "прикинуть бюджет и варианты"
    if wish.due_date:
        return "поставить напоминание за день"
    if wish.photo_file_id:
        return "добавить референс-картинку"
    return random.choice(MICRO_TIPS)


def build_summary_text(summary: SummaryData) -> str:
    total = summary.total
    if total == 0:
        return (
            "пока список пуст. запишите хотя бы одно тёплое желание — и бот напомнит через пару недель."
        )

    nearest = summary.nearest
    random_wish = summary.random_wish
    nearest_text = "ничего с точной датой пока нет"
    if nearest and nearest.due_date:
        nearest_text = f"{nearest.title} — {nearest.due_date.isoformat()}"
    spark_text = random_wish.title if random_wish else "что-то доброе и тёплое"
    tip = pick_micro_tip(random_wish)
    return (
        f"у вас в копилке ♥ {total} планов. ближе всего: {nearest_text}.\n"
        f"за эти две недели можно: {spark_text}. маленький шаг: {tip}.\n\n"
        "вы — команда. выберите один пункт и сделайте его на 1% реальнее."
    )


def parse_filters(args: Sequence[str]) -> Dict[str, str]:
    filters: Dict[str, str] = {}
    for arg in args:
        if "=" not in arg:
            continue
        key, value = arg.split("=", 1)
        value = value.strip().strip('"')
        filters[key.strip()] = value
    return filters


def tags_from_csv(csv_string: Optional[str]) -> List[str]:
    if not csv_string:
        return []
    return [part.strip() for part in csv_string.split(",") if part.strip()]
