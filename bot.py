from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from scheduler import init_scheduler
from storage import Storage, Wish
from utils import (
    SummaryData,
    TAG_OPTIONS,
    build_summary_text,
    ensure_initial_ping,
    format_wish_caption,
    parse_due_date,
    parse_filters,
    parse_price,
    tags_from_csv,
    toggle_tag,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEFAULT_TZ = os.getenv("TZ", "Europe/Sofia")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан. Проверьте .env")

storage = Storage()

TITLE, OPTIONS = range(2)

HORIZON_CODES = {
    "NOW": "⚡ Прямо сейчас",
    "MONTH": "📆 Этот месяц",
    "YEAR": "📅 Этот год",
    "SOMEDAY": "⏳ Когда-нибудь",
    "DATE": "🗓 Точная дата",
}

TAG_CODES = {f"TAG{i}": tag for i, tag in enumerate(TAG_OPTIONS)}

ADD_MAIN_TEXT = "Добавим детали? Всё опционально. Когда будете готовы — жмите ‘Сохранить’."


def wish_keyboard(wish_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("✅ Выполнено", callback_data=f"WISH:DONE:{wish_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"WISH:DEL:{wish_id}"),
        ],
        [
            InlineKeyboardButton("🏷 Теги", callback_data=f"WISH:TAGS:{wish_id}:MENU"),
            InlineKeyboardButton("⏰ Когда", callback_data=f"WISH:WHEN:{wish_id}:MENU"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def add_main_keyboard(temp: Dict[str, Any]) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("➕ Фото", callback_data="ADD:PHOTO"),
            InlineKeyboardButton("💰 Цена", callback_data="ADD:PRICE:MENU"),
            InlineKeyboardButton("⏰ Когда", callback_data="ADD:WHEN:MENU"),
        ],
        [
            InlineKeyboardButton("🏷 Теги", callback_data="ADD:TAGS:MENU"),
            InlineKeyboardButton("✅ Сохранить", callback_data="ADD:SAVE"),
        ],
        [InlineKeyboardButton("🚫 Отмена", callback_data="ADD:CANCEL")],
    ]
    return InlineKeyboardMarkup(buttons)


def add_price_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("Есть", callback_data="ADD:PRICE:HAS"), InlineKeyboardButton("Нет", callback_data="ADD:PRICE:NOT")],
        [InlineKeyboardButton("⬅ Назад", callback_data="ADD:BACK")],
    ]
    return InlineKeyboardMarkup(buttons)


def add_when_keyboard() -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for code, label in HORIZON_CODES.items():
        rows.append([InlineKeyboardButton(label, callback_data=f"ADD:WHEN:SET:{code}")])
    rows.append([InlineKeyboardButton("⬅ Назад", callback_data="ADD:BACK")])
    return InlineKeyboardMarkup(rows)


def add_tags_keyboard(temp: Dict[str, Any]) -> InlineKeyboardMarkup:
    selected = tags_from_csv(temp.get("tags"))
    rows: List[List[InlineKeyboardButton]] = []
    for code, tag in TAG_CODES.items():
        flag = "✅" if tag in selected else "➕"
        rows.append([InlineKeyboardButton(f"{flag} {tag}", callback_data=f"ADD:TAGS:TOGGLE:{code}")])
    rows.append([InlineKeyboardButton("Готово", callback_data="ADD:BACK")])
    return InlineKeyboardMarkup(rows)


def add_tags_keyboard_wish(wish_id: int, wish: Wish) -> InlineKeyboardMarkup:
    selected = tags_from_csv(wish.tags)
    rows: List[List[InlineKeyboardButton]] = []
    for code, tag in TAG_CODES.items():
        flag = "✅" if tag in selected else "➕"
        rows.append([InlineKeyboardButton(f"{flag} {tag}", callback_data=f"WISH:TAGS:{wish_id}:TOGGLE:{code}")])
    rows.append([InlineKeyboardButton("Готово", callback_data=f"WISH:TAGS:{wish_id}:CLOSE")])
    return InlineKeyboardMarkup(rows)


def add_when_keyboard_wish(wish_id: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=f"WISH:WHEN:{wish_id}:SET:{code}")] for code, label in HORIZON_CODES.items()]
    rows.append([InlineKeyboardButton("Отмена", callback_data=f"WISH:WHEN:{wish_id}:CLOSE")])
    return InlineKeyboardMarkup(rows)


async def ensure_chat_meta(chat_id: int) -> None:
    meta = await asyncio.to_thread(storage.get_or_init_chat_meta, chat_id, DEFAULT_TZ)
    if meta.next_ping_at is None:
        now = datetime.now(UTC)
        next_ping = ensure_initial_ping(now, meta.timezone)
        await asyncio.to_thread(storage.update_chat_meta, chat_id, next_ping_at=next_ping)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await ensure_chat_meta(chat_id)
    text = (
        "Привет! Я тёплый wishlist-бот. Команда /add начнёт добавление желания."
        " Всё, что мы записываем, остаётся внутри этого чата."
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Команды:\n"
        "/add — добавить новое желание\n"
        "/list — список текущих желаний\n"
        "/random — случайная идея\n"
        "/done <id> — отметить выполненным\n"
        "/delete <id> — удалить\n"
        "/summary — сводка по чату"
    )
    await update.message.reply_text(text)


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Как назовём желание? (до 120 символов)")
    return TITLE


async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Хорошо, останавливаемся. Если появится идея — /add.")
    return ConversationHandler.END


async def edit_add_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, keyboard: InlineKeyboardMarkup) -> None:
    message_id = context.user_data.get("add_message_id")
    if not message_id:
        sent = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
        context.user_data["add_message_id"] = sent.message_id
        return
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
        )
    except Exception:
        sent = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
        context.user_data["add_message_id"] = sent.message_id


async def add_receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = (update.message.text or "").strip()
    if not title:
        await update.message.reply_text("Нужно живое название. Попробуйте ещё раз.")
        return TITLE
    if len(title) > 120:
        await update.message.reply_text("Давайте чуть короче (до 120 символов).")
        return TITLE
    context.user_data["new_wish"] = {
        "title": title,
        "photo_file_id": None,
        "price_flag": False,
        "price_amount": None,
        "time_horizon": HORIZON_CODES["SOMEDAY"],
        "due_date": None,
        "tags": None,
    }
    await edit_add_message(context, update.effective_chat.id, ADD_MAIN_TEXT, add_main_keyboard(context.user_data["new_wish"]))
    return OPTIONS


async def restore_add_main(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    temp = context.user_data.get("new_wish", {})
    await edit_add_message(context, chat_id, ADD_MAIN_TEXT, add_main_keyboard(temp))


async def add_handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    temp = context.user_data.get("new_wish")
    if not temp:
        await query.edit_message_text("Диалог истёк. Запустите /add заново.")
        return ConversationHandler.END
    chat_id = query.message.chat.id

    if data == "ADD:PHOTO":
        context.user_data["awaiting_photo"] = True
        await edit_add_message(context, chat_id, "Пришлите фото. Можно пропустить.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Назад", callback_data="ADD:BACK")]]))
        return OPTIONS
    if data == "ADD:PRICE:MENU":
        await edit_add_message(context, chat_id, "Есть ли ориентир по цене?", add_price_keyboard())
        return OPTIONS
    if data == "ADD:PRICE:HAS":
        context.user_data["awaiting_price"] = True
        await edit_add_message(
            context,
            chat_id,
            "Напишите сумму (можно приблизительно). Если ничего не нужно — нажмите ‘Назад’.",
            InlineKeyboardMarkup([[InlineKeyboardButton("Пропустить", callback_data="ADD:PRICE:SKIP")], [InlineKeyboardButton("⬅ Назад", callback_data="ADD:BACK")]]),
        )
        return OPTIONS
    if data == "ADD:PRICE:NOT":
        temp["price_flag"] = False
        temp["price_amount"] = None
        context.user_data.pop("awaiting_price", None)
        await restore_add_main(context, chat_id)
        return OPTIONS
    if data == "ADD:PRICE:SKIP":
        temp["price_flag"] = True
        temp["price_amount"] = None
        context.user_data.pop("awaiting_price", None)
        await restore_add_main(context, chat_id)
        return OPTIONS
    if data == "ADD:WHEN:MENU":
        await edit_add_message(context, chat_id, "Когда хочется осуществить?", add_when_keyboard())
        return OPTIONS
    if data.startswith("ADD:WHEN:SET:"):
        code = data.split(":")[-1]
        label = HORIZON_CODES.get(code)
        if not label:
            await query.answer("Неизвестный вариант", show_alert=True)
            return OPTIONS
        temp["time_horizon"] = label
        if code == "DATE":
            context.user_data["awaiting_due"] = True
            temp["due_date"] = None
            await edit_add_message(
                context,
                chat_id,
                "Напишите дату в формате YYYY-MM-DD.",
                InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("Пропустить", callback_data="ADD:DUE:SKIP")],
                        [InlineKeyboardButton("⬅ Назад", callback_data="ADD:BACK")],
                    ]
                ),
            )
            return OPTIONS
        context.user_data.pop("awaiting_due", None)
        temp["due_date"] = None
        await restore_add_main(context, chat_id)
        return OPTIONS
    if data == "ADD:DUE:SKIP":
        temp["due_date"] = None
        context.user_data.pop("awaiting_due", None)
        await restore_add_main(context, chat_id)
        return OPTIONS
    if data == "ADD:TAGS:MENU":
        await edit_add_message(context, chat_id, "Выберите теги, можно несколько.", add_tags_keyboard(temp))
        return OPTIONS
    if data.startswith("ADD:TAGS:TOGGLE:"):
        code = data.split(":")[-1]
        tag = TAG_CODES.get(code)
        if tag:
            temp["tags"] = toggle_tag(temp.get("tags"), tag)
            await edit_add_message(context, chat_id, "Выберите теги, можно несколько.", add_tags_keyboard(temp))
        return OPTIONS
    if data == "ADD:BACK":
        context.user_data.pop("awaiting_price", None)
        context.user_data.pop("awaiting_due", None)
        context.user_data.pop("awaiting_photo", None)
        await restore_add_main(context, chat_id)
        return OPTIONS
    if data == "ADD:SAVE":
        wish = await save_new_wish(update, context, temp)
        if wish:
            await query.edit_message_text("Сохранила! Посмотрите карточку ниже.")
            await send_wish_card(context, chat_id, wish)
        context.user_data.clear()
        return ConversationHandler.END
    if data == "ADD:CANCEL":
        await query.edit_message_text("Хорошо, отменяем. Возвращайтесь с новой идеей.")
        context.user_data.clear()
        return ConversationHandler.END

    return OPTIONS


async def save_new_wish(update: Update, context: ContextTypes.DEFAULT_TYPE, temp: Dict[str, Any]) -> Optional[Wish]:
    user = update.effective_user
    chat_id = update.effective_chat.id
    wish = await asyncio.to_thread(
        storage.create_wish,
        chat_id=chat_id,
        user_id=user.id,
        user_username=user.username,
        user_first_name=user.first_name,
        title=temp["title"],
        photo_file_id=temp.get("photo_file_id"),
        price_flag=temp.get("price_flag", False),
        price_amount=temp.get("price_amount"),
        time_horizon=temp.get("time_horizon"),
        due_date=temp.get("due_date"),
        tags=temp.get("tags"),
    )
    return wish


async def add_receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not context.user_data.get("awaiting_photo"):
        return OPTIONS
    temp = context.user_data.get("new_wish")
    if not temp:
        await update.message.reply_text("Диалог завершён. Начните заново с /add.")
        return ConversationHandler.END
    photo = update.message.photo[-1]
    temp["photo_file_id"] = photo.file_id
    context.user_data.pop("awaiting_photo", None)
    await update.message.reply_text("Фото добавлено.")
    await restore_add_main(context, update.effective_chat.id)
    return OPTIONS


async def add_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    temp = context.user_data.get("new_wish")
    if not temp:
        await update.message.reply_text("Диалог завершён. Запустите /add снова.")
        return ConversationHandler.END
    if context.user_data.get("awaiting_price"):
        try:
            amount = parse_price(update.message.text)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return OPTIONS
        temp["price_flag"] = True
        temp["price_amount"] = amount
        context.user_data.pop("awaiting_price", None)
        await update.message.reply_text("Записала цену.")
        await restore_add_main(context, update.effective_chat.id)
        return OPTIONS
    if context.user_data.get("awaiting_due"):
        try:
            due = parse_due_date(update.message.text)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return OPTIONS
        temp["due_date"] = due
        context.user_data.pop("awaiting_due", None)
        await update.message.reply_text("Дата сохранена.")
        await restore_add_main(context, update.effective_chat.id)
        return OPTIONS
    await update.message.reply_text("Если хотите изменить название, начните заново с /add.")
    return OPTIONS


async def update_card_message(message, wish: Wish, keyboard: Optional[InlineKeyboardMarkup] = None) -> None:
    caption = format_wish_caption(wish)
    keyboard = keyboard or wish_keyboard(wish.id)
    if message.photo:
        await message.edit_caption(caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await message.edit_text(caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def edit_card_by_ids(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, wish: Wish, has_photo: bool, keyboard: Optional[InlineKeyboardMarkup] = None) -> None:
    caption = format_wish_caption(wish)
    keyboard = keyboard or wish_keyboard(wish.id)
    if has_photo:
        await context.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
    else:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )


async def send_wish_card(context: ContextTypes.DEFAULT_TYPE, chat_id: int, wish: Wish, message=None) -> None:
    caption = format_wish_caption(wish)
    keyboard = wish_keyboard(wish.id)
    if message:
        await update_card_message(message, wish, keyboard)
        return
    if wish.photo_file_id:
        await context.bot.send_photo(chat_id=chat_id, photo=wish.photo_file_id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    filters = parse_filters(context.args or [])
    context.chat_data["list_filters"] = filters
    try:
        page = int(filters.get("page", "1"))
    except ValueError:
        page = 1
    await send_list_page(update.message.chat.id, update, context, page=page)


async def send_list_page(chat_id: int, update_or_query, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    filters = context.chat_data.get("list_filters", {})
    status = filters.get("status")
    horizon = filters.get("horizon")
    limit = 10
    offset = (page - 1) * limit
    wishes, total = await asyncio.to_thread(
        storage.list_wishes,
        chat_id=chat_id,
        status=status,
        time_horizon=horizon,
        limit=limit,
        offset=offset,
    )
    if not wishes:
        text = "Пока пусто. Добавьте что-то через /add."
        if isinstance(update_or_query, Update) and update_or_query.message:
            await update_or_query.message.reply_text(text)
        else:
            await update_or_query.edit_message_text(text)
        return
    text_lines = [f"Страница {page}. Всего {total} записей."]
    for wish in wishes:
        text_lines.append(f"#{wish.id} — {wish.title} ({wish.time_horizon})")
    buttons: List[InlineKeyboardButton] = []
    if page > 1:
        buttons.append(InlineKeyboardButton("« Назад", callback_data=f"LIST:PAGE:{page-1}"))
    if offset + limit < total:
        buttons.append(InlineKeyboardButton("Дальше »", callback_data=f"LIST:PAGE:{page+1}"))
    markup = InlineKeyboardMarkup([buttons]) if buttons else None
    if isinstance(update_or_query, Update) and update_or_query.message:
        await update_or_query.message.reply_text("\n".join(text_lines), reply_markup=markup)
    else:
        await update_or_query.edit_message_text("\n".join(text_lines), reply_markup=markup)


async def list_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    page = int(query.data.split(":")[-1])
    await send_list_page(query.message.chat.id, query, context, page)


async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    wish = await asyncio.to_thread(storage.random_open_wish, chat_id)
    if not wish:
        await update.message.reply_text("Пока нет открытых желаний. /add спасёт ситуацию.")
        return
    await send_wish_card(context, chat_id, wish)


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    stats = await asyncio.to_thread(storage.count_stats, chat_id)
    random_wish = await asyncio.to_thread(storage.random_open_wish, chat_id)
    nearest = await asyncio.to_thread(storage.nearest_with_date, chat_id)
    summary = SummaryData(
        total=stats.get("total", 0),
        by_horizon=stats.get("by_horizon", {}),
        nearest=nearest,
        random_wish=random_wish,
    )
    await update.message.reply_text(build_summary_text(summary))


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Укажите id: /done 3")
        return
    try:
        wish_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("id должен быть числом")
        return
    wish = await asyncio.to_thread(storage.mark_done, wish_id)
    if not wish:
        await update.message.reply_text("Не нашла такое желание.")
        return
    await update.message.reply_text("Готово! Желание отмечено выполненным.")


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Укажите id: /delete 3")
        return
    try:
        wish_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("id должен быть числом")
        return
    ok = await asyncio.to_thread(storage.delete_wish, wish_id)
    if not ok:
        await update.message.reply_text("Не нашла такое желание.")
        return
    await update.message.reply_text("Удалено.")


async def wish_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    wish_id = int(query.data.split(":")[2])
    wish = await asyncio.to_thread(storage.mark_done, wish_id)
    if not wish:
        await query.edit_message_text("Это желание уже исчезло.")
        return
    await update_card_message(query.message, wish)


async def wish_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    wish_id = int(query.data.split(":")[2])
    ok = await asyncio.to_thread(storage.delete_wish, wish_id)
    if not ok:
        await query.edit_message_text("Желание уже удалено.")
        return
    if context.user_data.get("edit_due_wish") == wish_id:
        context.user_data.pop("edit_due_wish", None)
        context.user_data.pop("edit_due_message", None)
    if query.message.photo:
        await query.edit_message_caption(caption="Удалено.", reply_markup=None)
    else:
        await query.edit_message_text("Удалено.", reply_markup=None)


async def wish_when_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    wish_id = int(query.data.split(":")[2])
    wish = await asyncio.to_thread(storage.get_wish, wish_id)
    if not wish:
        await query.edit_message_text("Не нашла такое желание.")
        return
    await query.edit_message_reply_markup(reply_markup=add_when_keyboard_wish(wish_id))


async def wish_when_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    wish_id = int(parts[2])
    code = parts[4]
    wish = await asyncio.to_thread(storage.get_wish, wish_id)
    if not wish:
        await query.edit_message_text("Не нашла такое желание.")
        return
    label = HORIZON_CODES.get(code)
    if not label:
        await query.answer("Неизвестный вариант", show_alert=True)
        return
    if code == "DATE":
        context.user_data["edit_due_wish"] = wish_id
        context.user_data["edit_due_message"] = (
            query.message.chat.id,
            query.message.message_id,
            bool(query.message.photo),
        )
        await query.message.reply_text("Напишите дату YYYY-MM-DD для этого желания.")
        return
    context.user_data.pop("edit_due_wish", None)
    context.user_data.pop("edit_due_message", None)
    await asyncio.to_thread(storage.update_wish, wish_id, time_horizon=label, due_date=None)
    updated = await asyncio.to_thread(storage.get_wish, wish_id)
    await update_card_message(query.message, updated)


async def wish_when_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    wish_id = int(query.data.split(":")[2])
    wish = await asyncio.to_thread(storage.get_wish, wish_id)
    if not wish:
        await query.edit_message_text("Это желание уже удалено.")
        return
    context.user_data.pop("edit_due_wish", None)
    context.user_data.pop("edit_due_message", None)
    await update_card_message(query.message, wish)


async def wish_tags_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    wish_id = int(query.data.split(":")[2])
    wish = await asyncio.to_thread(storage.get_wish, wish_id)
    if not wish:
        await query.edit_message_text("Желание уже исчезло.")
        return
    await query.edit_message_reply_markup(reply_markup=add_tags_keyboard_wish(wish_id, wish))


async def wish_tags_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    wish_id = int(parts[2])
    code = parts[4]
    tag = TAG_CODES.get(code)
    if not tag:
        await query.answer("Неизвестный тег", show_alert=True)
        return
    wish = await asyncio.to_thread(storage.get_wish, wish_id)
    if not wish:
        await query.edit_message_text("Желание уже исчезло.")
        return
    new_tags = toggle_tag(wish.tags, tag)
    await asyncio.to_thread(storage.update_wish, wish_id, tags=new_tags)
    updated = await asyncio.to_thread(storage.get_wish, wish_id)
    await update_card_message(query.message, updated, add_tags_keyboard_wish(wish_id, updated))


async def wish_tags_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    wish_id = int(query.data.split(":")[2])
    wish = await asyncio.to_thread(storage.get_wish, wish_id)
    if not wish:
        await query.edit_message_text("Желание уже удалено.")
        return
    await update_card_message(query.message, wish)


async def global_text_listener(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("edit_due_wish"):
        wish_id = context.user_data.pop("edit_due_wish")
        message_info = context.user_data.pop("edit_due_message", None)
        try:
            due = parse_due_date(update.message.text)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            context.user_data["edit_due_wish"] = wish_id
            if message_info:
                context.user_data["edit_due_message"] = message_info
            return
        await asyncio.to_thread(storage.update_wish, wish_id, time_horizon=HORIZON_CODES["DATE"], due_date=due)
        updated = await asyncio.to_thread(storage.get_wish, wish_id)
        await update.message.reply_text("Дата обновлена.")
        if message_info:
            chat_id, message_id, has_photo = message_info
            await edit_card_by_ids(context, chat_id, message_id, updated, has_photo)
        else:
            await send_wish_card(context, update.effective_chat.id, updated)


def build_application():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_command)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_receive_title)],
            OPTIONS: [
                CallbackQueryHandler(add_handle_callback, pattern=r"^ADD:"),
                MessageHandler(filters.PHOTO, add_receive_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_receive_text),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_add)],
        name="add_conversation",
        persistent=False,
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CallbackQueryHandler(list_pagination, pattern=r"^LIST:PAGE:"))
    application.add_handler(CommandHandler("random", random_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CallbackQueryHandler(wish_done_callback, pattern=r"^WISH:DONE:"))
    application.add_handler(CallbackQueryHandler(wish_delete_callback, pattern=r"^WISH:DEL:"))
    application.add_handler(CallbackQueryHandler(wish_when_menu, pattern=r"^WISH:WHEN:.*:MENU$"))
    application.add_handler(CallbackQueryHandler(wish_when_set, pattern=r"^WISH:WHEN:\d+:SET:"))
    application.add_handler(CallbackQueryHandler(wish_when_close, pattern=r"^WISH:WHEN:\d+:CLOSE$"))
    application.add_handler(CallbackQueryHandler(wish_tags_menu, pattern=r"^WISH:TAGS:.*:MENU$"))
    application.add_handler(CallbackQueryHandler(wish_tags_toggle, pattern=r"^WISH:TAGS:\d+:TOGGLE:"))
    application.add_handler(CallbackQueryHandler(wish_tags_close, pattern=r"^WISH:TAGS:\d+:CLOSE$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_text_listener))

    return application


def main() -> None:
    application = build_application()
    init_scheduler(application, storage)
    logger.info("Бот запускается…")
    application.run_polling()


if __name__ == "__main__":
    main()
