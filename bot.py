from __future__ import annotations

import asyncio
import html
import logging
import os
import random
from datetime import datetime, timedelta
from typing import Dict, Optional

from dotenv import load_dotenv
from telegram import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from storage import (
    ChatMeta,
    Wish,
    count_stats,
    create_wish,
    delete_wish,
    get_or_init_chat_meta,
    get_wish,
    list_chats,
    list_wishes,
    mark_done,
    nearest_with_date,
    random_open_wish,
)
from utils import (
    MOTIVATION_PHRASES,
    RANDOM_IDEAS,
    TAG_OPTIONS,
    TIME_HORIZON_OPTIONS,
    build_summary_text,
    format_draft_price,
    format_draft_time,
    format_random_idea,
    format_wish_caption,
    parse_due_date,
    parse_price,
    tags_from_csv,
    toggle_tag,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEFAULT_TZ = os.getenv("TZ", "Europe/Moscow")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан. Создайте .env на основе .env.example")

ASK_TITLE, DETAILS = range(2)
ADD_CONV_HANDLER: Optional[ConversationHandler] = None
DRAFT_KEY = "new_wish"

TIME_CODES = {
    "NOW": "⚡ Прямо сейчас",
    "MONTH": "📆 Этот месяц",
    "YEAR": "📅 Этот год",
    "SOMEDAY": "⏳ Когда-нибудь",
    "DATE": "🗓 Точная дата",
}

BOTTOM_KEYBOARD = ReplyKeyboardMarkup(
    [["➕ Добавить", "📋 Список"], ["🎲 Рандом", "🧾 Сводка"]],
    resize_keyboard=True,
)


def _end_conversation_for_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    if ADD_CONV_HANDLER:
        ADD_CONV_HANDLER.conversations[(chat_id, user_id)] = ConversationHandler.END


def wish_action_keyboard(wish_id: int, done: bool = False) -> InlineKeyboardMarkup:
    if done:
        buttons = [[InlineKeyboardButton("🗑 Удалить", callback_data=f"WISH:DEL:{wish_id}")]]
    else:
        buttons = [
            [
                InlineKeyboardButton("✅ Выполнено", callback_data=f"WISH:DONE:{wish_id}"),
                InlineKeyboardButton("🗑 Удалить", callback_data=f"WISH:DEL:{wish_id}"),
            ]
        ]
    return InlineKeyboardMarkup(buttons)


def add_keyboard(draft: Dict[str, object]) -> InlineKeyboardMarkup:
    menu = draft.get("menu", "main")
    if menu == "price":
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Есть", callback_data="ADD:PRICE:SET:YES"),
                    InlineKeyboardButton("Нет", callback_data="ADD:PRICE:SET:NO"),
                ],
                [InlineKeyboardButton("⬅ Назад", callback_data="ADD:BACK")],
            ]
        )
    if menu == "when":
        rows = [
            [InlineKeyboardButton(label, callback_data=f"ADD:WHEN:SET:{code}")]
            for code, label in TIME_CODES.items()
        ]
        rows.append([InlineKeyboardButton("⬅ Назад", callback_data="ADD:BACK")])
        return InlineKeyboardMarkup(rows)
    if menu == "tags":
        selected = set(tags_from_csv(draft.get("tags")))
        rows = []
        for index, tag in enumerate(TAG_OPTIONS):
            flag = "✅" if tag in selected else "➕"
            rows.append(
                [InlineKeyboardButton(f"{flag} {tag}", callback_data=f"ADD:TAGS:TOGGLE:{index}")]
            )
        rows.append([InlineKeyboardButton("⬅ Назад", callback_data="ADD:BACK")])
        return InlineKeyboardMarkup(rows)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Фото", callback_data="ADD:PHOTO"),
                InlineKeyboardButton("💰 Цена", callback_data="ADD:PRICE:MENU"),
                InlineKeyboardButton("⏰ Когда", callback_data="ADD:WHEN:MENU"),
            ],
            [InlineKeyboardButton("🏷 Теги", callback_data="ADD:TAGS:MENU"), InlineKeyboardButton("✅ Сохранить", callback_data="ADD:SAVE")],
            [InlineKeyboardButton("🚫 Отмена", callback_data="ADD:CANCEL")],
        ]
    )


def draft_preview_text(draft: Dict[str, object]) -> str:
    title = html.escape(str(draft.get("title") or "—"))
    photo = "Есть" if draft.get("photo_file_id") else "Нет"
    price = format_draft_price(draft.get("price_flag"), draft.get("price_amount"))
    when = format_draft_time(draft.get("time_horizon"), draft.get("due_date"))
    tags = ", ".join(tags_from_csv(draft.get("tags"))) or "—"
    parts = [
        "<b>Черновик желания</b>",
        f"Название: <b>{title}</b>",
        f"Фото: {photo}",
        f"Цена: {html.escape(str(price))}",
        f"Когда: {html.escape(when)}",
        f"Теги: {html.escape(tags)}",
    ]
    return "\n".join(parts)


async def refresh_draft_message(context: ContextTypes.DEFAULT_TYPE, draft: Dict[str, object]) -> None:
    message_id = draft.get("message_id")
    chat_id = draft.get("message_chat_id")
    if not message_id or not chat_id:
        return
    try:
        await context.bot.edit_message_text(
            text=draft_preview_text(draft),
            chat_id=chat_id,
            message_id=message_id,
            parse_mode=ParseMode.HTML,
            reply_markup=add_keyboard(draft),
        )
    except BadRequest as exc:
        logger.debug("Не удалось обновить черновик: %s", exc)


async def ensure_chat_meta(chat_id: int) -> ChatMeta:
    return await asyncio.to_thread(get_or_init_chat_meta, chat_id, DEFAULT_TZ)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await ensure_chat_meta(chat_id)
    text = (
        "Привет! Я романтичный wishlist-бот. Жмите «➕ Добавить», чтобы записать идею,"
        " а /help подскажет команды."
    )
    await update.effective_message.reply_text(text, reply_markup=BOTTOM_KEYBOARD)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        await ensure_chat_meta(update.effective_chat.id)
    text = (
        "Команды:\n"
        "/add — добавить новое желание\n"
        "/list — показать текущий список\n"
        "/random — идея из локального банка\n"
        "/summary — короткая сводка\n"
        "/done <id> — отметить выполненным (только админы)\n"
        "/delete <id> — удалить (только админы)"
    )
    await update.effective_message.reply_text(text, reply_markup=BOTTOM_KEYBOARD)


async def add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    await ensure_chat_meta(chat_id)
    draft = {
        "chat_id": chat_id,
        "title": None,
        "photo_file_id": None,
        "price_flag": None,
        "price_amount": None,
        "time_horizon": None,
        "due_date": None,
        "tags": "",
        "awaiting": None,
        "menu": "main",
        "message_id": None,
        "message_chat_id": None,
    }
    context.user_data[DRAFT_KEY] = draft
    reply_markup = ForceReply(selective=True, input_field_placeholder="Название желания (до 120 символов)")
    await update.effective_message.reply_text(
        "Как назовём желание? Ответьте реплаем на это сообщение 💡",
        reply_markup=reply_markup,
    )
    return ASK_TITLE


async def add_receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    draft = context.user_data.get(DRAFT_KEY)
    if not message or not draft:
        return ConversationHandler.END
    if not message.reply_to_message or message.reply_to_message.from_user.id != context.bot.id:
        return ASK_TITLE
    title = message.text.strip()
    if not title:
        await message.reply_text(
            "Нужно придумать название. Попробуйте ещё раз 💡",
            reply_markup=ForceReply(selective=True, input_field_placeholder="Название желания"),
        )
        return ASK_TITLE
    if len(title) > 120:
        await message.reply_text(
            "Название должно быть короче 120 символов. Давайте чуть компактнее ✂️",
            reply_markup=ForceReply(selective=True, input_field_placeholder="Краткое название"),
        )
        return ASK_TITLE
    draft["title"] = title
    preview = draft_preview_text(draft)
    keyboard = add_keyboard(draft)
    sent = await message.reply_text(preview, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    draft["message_id"] = sent.message_id
    draft["message_chat_id"] = sent.chat_id
    return DETAILS


async def add_handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = context.user_data.get(DRAFT_KEY)
    if not draft:
        return ConversationHandler.END
    if draft.get("awaiting") != "photo":
        return DETAILS
    message = update.message
    if not message or not message.photo:
        return DETAILS
    photo = message.photo[-1]
    draft["photo_file_id"] = photo.file_id
    draft["awaiting"] = None
    await message.reply_text("Фото добавлено. Красота! 📸")
    await refresh_draft_message(context, draft)
    return DETAILS


async def add_handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = context.user_data.get(DRAFT_KEY)
    if not draft:
        return ConversationHandler.END
    awaiting = draft.get("awaiting")
    message = update.message
    if message is None:
        return DETAILS
    text = message.text.strip() if message.text else ""
    if awaiting == "price":
        try:
            parsed = parse_price(text)
        except ValueError as exc:
            await message.reply_text(str(exc))
            return DETAILS
        draft["price_flag"] = True
        draft["price_amount"] = str(parsed)
        draft["awaiting"] = None
        await message.reply_text("Записала сумму 💸")
        await refresh_draft_message(context, draft)
        return DETAILS
    if awaiting == "due_date":
        try:
            due = parse_due_date(text)
        except ValueError as exc:
            await message.reply_text(str(exc))
            return DETAILS
        draft["due_date"] = due
        draft["time_horizon"] = TIME_CODES["DATE"]
        draft["awaiting"] = None
        await message.reply_text("Дата отмечена ✨")
        await refresh_draft_message(context, draft)
        return DETAILS
    if awaiting == "photo":
        await message.reply_text("Пришлите фото изображением, оно заменит текущее.")
        return DETAILS
    if text:
        await message.reply_text("Используйте кнопки под черновиком, чтобы добавить детали.")
    return DETAILS


async def add_cancel(context: ContextTypes.DEFAULT_TYPE, draft: Dict[str, object]) -> None:
    message_id = draft.get("message_id")
    chat_id = draft.get("message_chat_id")
    if message_id and chat_id:
        try:
            await context.bot.edit_message_text(
                "Черновик отменён. До новых идей 💛",
                chat_id=chat_id,
                message_id=message_id,
            )
        except BadRequest:
            pass
    context.user_data.pop(DRAFT_KEY, None)


async def add_save(query_update: Update, context: ContextTypes.DEFAULT_TYPE, draft: Dict[str, object]) -> None:
    query = query_update.callback_query
    if not draft.get("title"):
        await query.answer(
            "Нужно придумать название. Без него идея не сохранится 💡",
            show_alert=True,
        )
        return
    chat_id = draft["chat_id"]
    user = query.from_user
    wish = await asyncio.to_thread(
        create_wish,
        chat_id=chat_id,
        user_id=user.id,
        user_first_name=user.first_name,
        user_username=user.username,
        title=str(draft["title"]),
        photo_file_id=draft.get("photo_file_id"),
        price_flag=draft.get("price_flag"),
        price_amount=draft.get("price_amount"),
        time_horizon=draft.get("time_horizon"),
        due_date=draft.get("due_date"),
        tags=draft.get("tags") or None,
    )

    message_id = draft.get("message_id")
    message_chat_id = draft.get("message_chat_id")
    if message_id and message_chat_id:
        try:
            await context.bot.edit_message_reply_markup(chat_id=message_chat_id, message_id=message_id, reply_markup=None)
        except BadRequest:
            pass
    context.user_data.pop(DRAFT_KEY, None)

    caption = format_wish_caption(wish)
    keyboard = wish_action_keyboard(wish.id)
    if wish.photo_file_id:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=wish.photo_file_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    _end_conversation_for_user(context, chat_id, user.id)

    await query.answer("Желание сохранено ✨")


async def add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    draft = context.user_data.get(DRAFT_KEY)
    if not draft:
        await query.answer("Черновик не найден. Начните заново через /add.", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except BadRequest:
            pass
        return
    data = query.data.split(":")
    if len(data) < 2:
        await query.answer()
        return

    action = data[1]

    if action == "PHOTO":
        draft["awaiting"] = "photo"
        draft["menu"] = "main"
        await refresh_draft_message(context, draft)
        if query.message:
            await query.message.reply_text(
                "Пришлите одно фото отдельным сообщением — оно попадёт в карточку. 📸"
            )
        await query.answer("Жду фото 📸")
        return

    if action == "PRICE":
        if len(data) == 3 and data[2] == "MENU":
            draft["menu"] = "price"
            await refresh_draft_message(context, draft)
            await query.answer()
            return
        if len(data) == 4 and data[2] == "SET":
            choice = data[3]
            if choice == "YES":
                draft["price_flag"] = True
                draft["price_amount"] = None
                draft["awaiting"] = "price"
                draft["menu"] = "main"
                await refresh_draft_message(context, draft)
                if query.message:
                    await query.message.reply_text("Напишите сумму или ориентир стоимости 💸")
                await query.answer("Введите сумму")
                return
            if choice == "NO":
                draft["price_flag"] = False
                draft["price_amount"] = None
                draft["awaiting"] = None
                draft["menu"] = "main"
                await refresh_draft_message(context, draft)
                await query.answer("Отмечено: без бюджета")
                return

    if action == "WHEN":
        if len(data) == 3 and data[2] == "MENU":
            draft["menu"] = "when"
            await refresh_draft_message(context, draft)
            await query.answer()
            return
        if len(data) == 4 and data[2] == "SET":
            code = data[3]
            label = TIME_CODES.get(code)
            if not label:
                await query.answer()
                return
            draft["time_horizon"] = label
            draft["menu"] = "main"
            if code == "DATE":
                draft["due_date"] = None
                draft["awaiting"] = "due_date"
                await refresh_draft_message(context, draft)
                if query.message:
                    await query.message.reply_text("Введите дату в формате YYYY-MM-DD.")
                await query.answer("Жду дату")
                return
            draft["due_date"] = None
            draft["awaiting"] = None
            await refresh_draft_message(context, draft)
            await query.answer("Срок обновлён")
            return

    if action == "TAGS":
        if len(data) == 3 and data[2] == "MENU":
            draft["menu"] = "tags"
            await refresh_draft_message(context, draft)
            await query.answer()
            return
        if len(data) == 4 and data[2] == "TOGGLE":
            try:
                index = int(data[3])
            except ValueError:
                await query.answer()
                return
            if 0 <= index < len(TAG_OPTIONS):
                tag = TAG_OPTIONS[index]
                draft["tags"] = toggle_tag(draft.get("tags"), tag)
                await refresh_draft_message(context, draft)
                active = tag in tags_from_csv(draft.get("tags"))
                await query.answer("Тег добавлен" if active else "Тег убран")
                return
            await query.answer()
            return

    if action == "SAVE":
        await add_save(update, context, draft)
        return

    if action == "CANCEL":
        await add_cancel(context, draft)
        if update.effective_chat and update.effective_user:
            _end_conversation_for_user(
                context, update.effective_chat.id, update.effective_user.id
            )
        await query.answer("Черновик отменён")
        return

    if action == "BACK":
        draft["menu"] = "main"
        await refresh_draft_message(context, draft)
        await query.answer()
        return

    await query.answer()


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_list_page(update, context, page=0)


def build_list_text(wishes: list[Wish], page: int, total: int, per_page: int) -> str:
    if not total:
        return "Пока пусто. Добавить через /add или кнопку «➕ Добавить»."
    lines = ["<b>Список желаний</b>"]
    for wish in wishes:
        horizon = wish.time_horizon or "Без срока"
        if wish.due_date:
            horizon = f"{horizon} — {wish.due_date.isoformat()}"
        lines.append(f"#{wish.id} — {html.escape(wish.title)} ({html.escape(horizon)})")
    total_pages = max(1, (total + per_page - 1) // per_page)
    lines.append(f"Стр. {page + 1} из {total_pages}")
    return "\n".join(lines)


def list_keyboard(page: int, total: int, per_page: int) -> Optional[InlineKeyboardMarkup]:
    total_pages = max(1, (total + per_page - 1) // per_page)
    if total_pages <= 1:
        return None
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("« Назад", callback_data=f"LIST:{page - 1}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Дальше »", callback_data=f"LIST:{page + 1}"))
    return InlineKeyboardMarkup([buttons]) if buttons else None


async def send_list_page(update_or_query: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    chat = update_or_query.effective_chat
    if not chat:
        return
    chat_id = chat.id
    await ensure_chat_meta(chat_id)
    per_page = 10
    wishes, total = await asyncio.to_thread(list_wishes, chat_id, "open", None, per_page, page * per_page)
    text = build_list_text(wishes, page, total, per_page)
    keyboard = list_keyboard(page, total, per_page)
    if update_or_query.callback_query:
        try:
            await update_or_query.callback_query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        except BadRequest:
            pass
        return
    await update_or_query.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        page = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        return
    await send_list_page(update, context, page)


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return
    chat_id = chat.id
    await ensure_chat_meta(chat_id)
    stats_task = asyncio.to_thread(count_stats, chat_id)
    nearest_task = asyncio.to_thread(nearest_with_date, chat_id)
    random_task = asyncio.to_thread(random_open_wish, chat_id)
    stats, nearest, random_wish_obj = await asyncio.gather(
        stats_task, nearest_task, random_task
    )
    payload = {
        "total_open": stats.get("total_open", 0),
        "by_horizon": stats.get("by_horizon", {}),
        "nearest": nearest,
        "random": random_wish_obj,
        "motivation": random.choice(MOTIVATION_PHRASES),
    }
    text = build_summary_text(payload)
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


def random_keyboard(index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("❤️ Берём", callback_data=f"RAND:TAKE:{index}")],
            [InlineKeyboardButton("🔁 Дай другое", callback_data="RAND:NEXT")],
            [InlineKeyboardButton("🚫 Закрыть", callback_data="RAND:CLOSE")],
        ]
    )


async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat:
        await ensure_chat_meta(chat.id)
    index = random.randrange(len(RANDOM_IDEAS))
    idea = RANDOM_IDEAS[index]
    text = format_random_idea(idea)
    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=random_keyboard(index),
    )


async def random_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    action = parts[1]
    if action == "NEXT":
        index = random.randrange(len(RANDOM_IDEAS))
        text = format_random_idea(RANDOM_IDEAS[index])
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=random_keyboard(index))
        await query.answer("Вот ещё идея! ✨")
        return
    if action == "CLOSE":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.answer("Закрыто")
        return
    if action == "TAKE":
        try:
            index = int(parts[2])
        except (IndexError, ValueError):
            await query.answer("Что-то пошло не так", show_alert=True)
            return
        idea = RANDOM_IDEAS[index]
        if not query.message or not query.message.chat:
            await query.answer("Не удалось определить чат", show_alert=True)
            return
        chat_id = query.message.chat.id
        await ensure_chat_meta(chat_id)
        user = query.from_user
        tags_csv = ",".join(idea.get("tags", [])) or None
        wish = await asyncio.to_thread(
            create_wish,
            chat_id=chat_id,
            user_id=user.id,
            user_first_name=user.first_name,
            user_username=user.username,
            title=str(idea["title"]),
            photo_file_id=None,
            price_flag=False,
            price_amount=None,
            time_horizon=idea.get("default_horizon"),
            due_date=None,
            tags=tags_csv,
        )
        caption = format_wish_caption(wish)
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=wish_action_keyboard(wish.id),
        )
        await query.answer("Добавила в список ❤️")
        return


async def wish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    if len(parts) < 3:
        await query.answer()
        return
    action, wish_id_raw = parts[1], parts[2]
    try:
        wish_id = int(wish_id_raw)
    except ValueError:
        await query.answer()
        return
    if not query.message or not query.message.chat:
        await query.answer("Не удалось определить чат", show_alert=True)
        return
    chat = query.message.chat
    chat_id = chat.id
    user_id = query.from_user.id
    if not await user_can_manage(chat_id, user_id, context, chat.type):
        await query.answer("Только администраторы могут это делать.", show_alert=True)
        return
    if action == "DONE":
        wish = await asyncio.to_thread(mark_done, wish_id)
        if not wish or wish.chat_id != chat_id:
            await query.answer("Запись не найдена", show_alert=True)
            return
        caption = format_wish_caption(wish)
        keyboard = wish_action_keyboard(wish.id, done=True)
        if query.message.photo:
            await query.edit_message_caption(caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        else:
            await query.edit_message_text(caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        await query.answer("Готово! 💫")
    elif action == "DEL":
        ok = await asyncio.to_thread(delete_wish, wish_id)
        if not ok:
            await query.answer("Не получилось удалить", show_alert=True)
            return
        try:
            await query.message.delete()
        except (BadRequest, Forbidden):
            await query.edit_message_text("Запись удалена.")
        await query.answer("Удалено 🗑")
    else:
        await query.answer()


async def user_can_manage(
    chat_id: int,
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    chat_type: Optional[str] = None,
) -> bool:
    if chat_type is None:
        try:
            chat = await context.bot.get_chat(chat_id)
        except Exception:
            return False
        chat_type = chat.type

    if chat_type == "private":
        return True

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in {"creator", "administrator"}


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Использование: /done <id>")
        return
    try:
        wish_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("ID должен быть числом.")
        return
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return
    chat_id = chat.id
    await ensure_chat_meta(chat_id)
    if not await user_can_manage(chat_id, user.id, context, chat.type):
        await update.effective_message.reply_text("Только администраторы могут отмечать выполненным.")
        return
    wish = await asyncio.to_thread(mark_done, wish_id)
    if not wish or wish.chat_id != chat_id:
        await update.effective_message.reply_text("Желание не найдено в этом чате.")
        return
    await update.effective_message.reply_text(f"Желание #{wish.id} отмечено выполненным ✅")


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Использование: /delete <id>")
        return
    try:
        wish_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("ID должен быть числом.")
        return
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return
    chat_id = chat.id
    await ensure_chat_meta(chat_id)
    if not await user_can_manage(chat_id, user.id, context, chat.type):
        await update.effective_message.reply_text("Только администраторы могут удалять желания.")
        return
    ok = await asyncio.to_thread(delete_wish, wish_id)
    if not ok:
        await update.effective_message.reply_text("Запись не найдена.")
        return
    await update.effective_message.reply_text(f"Желание #{wish_id} удалено 🗑")


async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    if text == "📋 Список":
        await list_command(update, context)
    elif text == "🎲 Рандом":
        await random_command(update, context)
    elif text == "🧾 Сводка":
        await summary_command(update, context)


async def add_job_biweekly(context: ContextTypes.DEFAULT_TYPE) -> None:
    chats = await asyncio.to_thread(list_chats)
    now = datetime.utcnow()
    for chat in chats:
        last_added = chat.last_added_at or chat.created_at
        if not last_added or now - last_added >= timedelta(days=14):
            idea = random.choice(RANDOM_IDEAS)
            text = (
                "Вы классные 💞 Добавим маленькую хотелку? ✨\n"
                f"• {idea['title']} — {idea['description']}"
            )
            try:
                await context.bot.send_message(chat.chat_id, text)
            except Exception as exc:  # pragma: no cover - уведомления должны быть мягкими
                logger.debug("Не удалось отправить напоминание: %s", exc)


async def add_job_monthly(context: ContextTypes.DEFAULT_TYPE) -> None:
    chats = await asyncio.to_thread(list_chats)
    for chat in chats:
        stats_task = asyncio.to_thread(count_stats, chat.chat_id)
        nearest_task = asyncio.to_thread(nearest_with_date, chat.chat_id)
        random_task = asyncio.to_thread(random_open_wish, chat.chat_id)
        stats, nearest, random_wish_obj = await asyncio.gather(
            stats_task, nearest_task, random_task
        )
        header = (
            f"У вас уже {stats.get('total_open', 0)} тёплых планов 💖"
            if stats.get("total_open", 0)
            else "Пока в списке пусто — самое время добавить что-то доброе!"
        )
        payload = {
            "total_open": stats.get("total_open", 0),
            "by_horizon": stats.get("by_horizon", {}),
            "nearest": nearest,
            "random": random_wish_obj,
            "motivation": random.choice(MOTIVATION_PHRASES),
        }
        body = build_summary_text(payload)
        try:
            await context.bot.send_message(
                chat.chat_id,
                f"{header}\n\n{body}",
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:  # pragma: no cover
            logger.debug("Не удалось отправить ежемесячную сводку: %s", exc)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Произошла ошибка при обработке апдейта: %s", context.error)


async def post_init(application: Application) -> None:
    application.job_queue.run_repeating(
        add_job_biweekly,
        interval=14 * 24 * 60 * 60,
        first=60,
        name="biweekly_reminder",
        misfire_grace_time=300,
    )
    application.job_queue.run_repeating(
        add_job_monthly,
        interval=30 * 24 * 60 * 60,
        first=120,
        name="monthly_summary",
        misfire_grace_time=300,
    )


def build_application() -> Application:
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .parse_mode(ParseMode.HTML)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    global ADD_CONV_HANDLER
    ADD_CONV_HANDLER = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_entry),
            MessageHandler(filters.Regex(r"^➕ Добавить$"), add_entry),
        ],
        states={
            ASK_TITLE: [MessageHandler(filters.TEXT & filters.REPLY & ~filters.COMMAND, add_receive_title)],
            DETAILS: [
                MessageHandler(filters.PHOTO, add_handle_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_handle_text),
            ],
        },
        fallbacks=[],
        allow_reentry=True,
        per_chat=True,
        per_user=True,
    )
    application.add_handler(ADD_CONV_HANDLER)

    application.add_handler(CallbackQueryHandler(add_callback, pattern=r"^ADD:"))
    application.add_handler(MessageHandler(filters.Regex(r"^(📋 Список|🎲 Рандом|🧾 Сводка)$"), handle_menu_buttons))

    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("random", random_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("delete", delete_command))

    application.add_handler(CallbackQueryHandler(list_callback, pattern=r"^LIST:"))
    application.add_handler(CallbackQueryHandler(random_callback, pattern=r"^RAND:"))
    application.add_handler(CallbackQueryHandler(wish_callback, pattern=r"^WISH:"))

    application.add_error_handler(error_handler)
    return application


def main() -> None:
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
