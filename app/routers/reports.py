"""Reporting commands."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from typing import List

import pytz
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from ..charts import build_checkin_chart
from ..config import settings
from ..db import async_session_factory
from ..models import Chat, Checkin, CheckinType, DailyStat, Membership, RoleEnum, User

router = Router(name="reports")

PERIODS = {
    "today": ("Сегодня", lambda tz: (datetime.now(tz).date(), datetime.now(tz).date())),
    "week": ("Неделя", lambda tz: (datetime.now(tz).date() - timedelta(days=6), datetime.now(tz).date())),
    "month": ("Месяц", lambda tz: (datetime.now(tz).date() - timedelta(days=29), datetime.now(tz).date())),
    "halfyear": ("Полгода", lambda tz: (datetime.now(tz).date() - timedelta(days=182), datetime.now(tz).date())),
}


def _report_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"report:period:{key}")]
        for key, (label, _) in PERIODS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("report"))
async def report_command(message: Message) -> None:
    await message.answer("Выберите период", reply_markup=_report_keyboard())


@router.message(Command("dashboard"))
async def dashboard_command(message: Message) -> None:
    await message.answer("Дашборд", reply_markup=_report_keyboard())


@router.callback_query(F.data.startswith("report:period"))
async def handle_report(callback: CallbackQuery) -> None:
    _, _, period_key = callback.data.split(":")
    label, builder = PERIODS[period_key]
    async with async_session_factory() as session:
        if callback.from_user.id == settings.owner_telegram_id:
            tz = pytz.timezone(settings.timezone)
            date_from, date_to = builder(tz)
            stats_stmt = (
                select(DailyStat)
                .where(DailyStat.date.between(date_from, date_to))
                .order_by(DailyStat.date)
            )
            stats_res = await session.execute(stats_stmt)
            stats = stats_res.scalars().all()
            if not stats:
                await callback.answer("Нет данных", show_alert=True)
                return
            aggregated = _aggregate_stats(stats)
            chart = build_checkin_chart(
                [row["date"] for row in aggregated],
                [row["morning"] for row in aggregated],
                [row["evening"] for row in aggregated],
            )
            csv_buffer = _build_csv_export(stats)
            total_ops = sum(row.total_operators for row in stats)
            caption = (
                f"Сводный отчёт: {label}\n"
                f"Период: {date_from} — {date_to}\n"
                f"Всего операторов: {total_ops}"
            )
        else:
            membership_stmt = (
                select(Membership, User, Chat)
                .join(User)
                .join(Chat)
                .where(User.telegram_id == callback.from_user.id)
            )
            membership_res = await session.execute(membership_stmt)
            membership = membership_res.first()
            if not membership:
                await callback.answer("Нет авторизации", show_alert=True)
                return
            membership_obj: Membership = membership[0]
            chat: Chat = membership[2]
            tz = pytz.timezone(chat.timezone)
            date_from, date_to = builder(tz)
            stats_stmt = (
                select(DailyStat)
                .where(
                    DailyStat.chat_id == membership_obj.chat_id,
                    DailyStat.date.between(date_from, date_to),
                )
                .order_by(DailyStat.date)
            )
            stats_res = await session.execute(stats_stmt)
            stats = stats_res.scalars().all()
            if not stats:
                await callback.answer("Нет данных", show_alert=True)
                return
            chart = build_checkin_chart(
                [row.date for row in stats],
                [row.morning_cnt for row in stats],
                [row.evening_cnt for row in stats],
            )
            csv_buffer = _build_csv_export(stats)
            caption = (
                f"Отчёт: {label}\n"
                f"Период: {date_from} — {date_to}\n"
                f"Операторов: {stats[-1].total_operators}"
            )
        await callback.message.answer_photo(
            BufferedInputFile(chart.getvalue(), filename="report.png"),
            caption=caption,
        )
        await callback.message.answer_document(
            BufferedInputFile(csv_buffer.getvalue().encode("utf-8"), filename="report.csv"),
            caption="Экспорт",
        )
    await callback.answer()


@router.message(Command("chats"))
async def chats_overview(message: Message) -> None:
    async with async_session_factory() as session:
        stmt = (
            select(Membership, DailyStat, Chat)
            .join(Chat)
            .join(DailyStat, DailyStat.chat_id == Chat.id)
            .join(User, Membership.user_id == User.id)
            .where(User.telegram_id == message.from_user.id)
            .order_by(DailyStat.date.desc())
        )
        res = await session.execute(stmt)
        rows = res.all()
        if not rows:
            await message.answer("Нет статистики")
            return
        lines = []
        for membership, stat, chat in rows:
            lines.append(
                f"Чат: {chat.title or chat.chat_id}, дата {stat.date}: утро {stat.morning_cnt}, вечер {stat.evening_cnt}"
            )
        await message.answer("\n".join(lines))


@router.message(Command("export"))
async def export_command(message: Message) -> None:
    async with async_session_factory() as session:
        stmt = (
            select(Membership, User, Chat)
            .join(User)
            .join(Chat)
            .where(User.telegram_id == message.from_user.id)
        )
        res = await session.execute(stmt)
        membership = res.first()
        if not membership:
            await message.answer("Нет доступа")
            return
        membership_obj: Membership = membership[0]
        chat: Chat = membership[2]
        checkins_stmt = select(Checkin, User).join(User).where(Checkin.chat_id == chat.id)
        checkins_res = await session.execute(checkins_stmt)
        rows = checkins_res.all()
        csv_file = io.StringIO()
        writer = csv.writer(csv_file)
        writer.writerow(["date", "user", "chat", "type", "status"])
        for checkin, user in rows:
            writer.writerow([
                checkin.checkin_date,
                user.full_name or user.username or user.telegram_id,
                chat.chat_id,
                checkin.type.value,
                "done",
            ])
        await message.answer_document(
            BufferedInputFile(csv_file.getvalue().encode("utf-8"), filename="export.csv"),
            caption="Экспорт",
        )


def _build_csv_export(stats: List[DailyStat]) -> io.StringIO:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "morning", "evening", "total", "misses"])
    for row in stats:
        writer.writerow([row.date, row.morning_cnt, row.evening_cnt, row.total_operators, row.misses])
    buffer.seek(0)
    return buffer


def _aggregate_stats(stats: List[DailyStat]) -> List[dict]:
    aggregated: dict[date, dict[str, int]] = {}
    for row in stats:
        bucket = aggregated.setdefault(row.date, {"morning": 0, "evening": 0})
        bucket["morning"] += row.morning_cnt
        bucket["evening"] += row.evening_cnt
    return [
        {"date": day, "morning": values["morning"], "evening": values["evening"]}
        for day, values in sorted(aggregated.items())
    ]
