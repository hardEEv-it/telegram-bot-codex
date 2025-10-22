from __future__ import annotations

import html
from datetime import date
from typing import Dict, List, Optional

from storage import Wish

TAG_OPTIONS = [
    "Личное",
    "Для нас двоих",
    "Подарок",
    "Спонтанно",
    "Большая мечта",
]

TIME_HORIZON_OPTIONS = [
    "⚡ Прямо сейчас",
    "📆 Этот месяц",
    "📅 Этот год",
    "⏳ Когда-нибудь",
    "🗓 Точная дата",
]

MOTIVATION_PHRASES = [
    "Вы классная команда — маленькие шаги дарят тепло.",
    "Нежность в планах превращается в воспоминания.",
    "Каждая идея — повод обнять друг друга.",
    "Вы создаёте свою сказку, пункт за пунктом.",
    "Запланируйте радость — и день станет мягче.",
    "Ваша забота друг о друге уже вдохновляет.",
    "Добавьте что-то милое — и появится новая искра.",
    "Доверяйте своим желаниям, они про любовь.",
    "Общее дело сближает сильнее любых слов.",
    "Небольшая хотелка сегодня — уют завтра.",
    "Любовь любит конкретику — запишите её.",
    "Маленький план превращает мечту в действие.",
]

RANDOM_IDEAS: List[Dict[str, object]] = [
    {
        "title": "Ночь настольных игр",
        "description": "Выключить телефоны, заварить чай и играть до утра ☕️",
        "tags": ["Для нас двоих", "Спонтанно"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Совместный плейлист",
        "description": "Собрать 20 песен, которые напоминают о вас двоих.",
        "tags": ["Для нас двоих", "Личное"],
        "default_horizon": "⚡ Прямо сейчас",
    },
    {
        "title": "Мини-пикник дома",
        "description": "Разложить плед, приготовить закуски и винтажные бокалы.",
        "tags": ["Для нас двоих", "Спонтанно"],
        "default_horizon": "⚡ Прямо сейчас",
    },
    {
        "title": "Письма благодарности",
        "description": "Написать друг другу короткие письма о том, за что вы благодарны.",
        "tags": ["Личное"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Фотосессия на старый телефон",
        "description": "Сделать серию забавных и тёплых кадров на плёночную камеру или ретро-фильтр.",
        "tags": ["Спонтанно", "Для нас двоих"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Тематический вечер кухни",
        "description": "Выбрать страну и приготовить вместе её фирменные блюда.",
        "tags": ["Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Карта совместных мечтаний",
        "description": "Создать коллаж из вырезок и картинок о том, что хочется прожить вместе.",
        "tags": ["Большая мечта", "Для нас двоих"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Утренний сюрприз",
        "description": "Проснуться чуть раньше и приготовить завтрак в постель.",
        "tags": ["Подарок", "Спонтанно"],
        "default_horizon": "⚡ Прямо сейчас",
    },
    {
        "title": "Список " + "100" + " желаний",
        "description": "Заполнить большой список общих мечт, пусть даже самых смелых.",
        "tags": ["Большая мечта", "Для нас двоих"],
        "default_horizon": "⏳ Когда-нибудь",
    },
    {
        "title": "Совместная тренировка",
        "description": "Сделать зарядку или растяжку под любимый плейлист.",
        "tags": ["Для нас двоих", "Спонтанно"],
        "default_horizon": "⚡ Прямо сейчас",
    },
    {
        "title": "Ночь сериалов",
        "description": "Выбрать мини-сериал и устроить марафон с попкорном.",
        "tags": ["Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Письмо в будущее",
        "description": "Написать себе через год и спрятать конверт до определённой даты.",
        "tags": ["Личное", "Большая мечта"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Прогулка без маршрута",
        "description": "Выйти и идти туда, куда потянет настроение, фотографируя детали.",
        "tags": ["Спонтанно", "Для нас двоих"],
        "default_horizon": "⚡ Прямо сейчас",
    },
    {
        "title": "Домашний планетарий",
        "description": "Повесить гирлянды, включить музыку космоса и обсуждать звёзды.",
        "tags": ["Для нас двоих", "Спонтанно"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Дегустация чая",
        "description": "Купить несколько новых сортов чая и устроить собственную дегустацию.",
        "tags": ["Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Квест воспоминаний",
        "description": "Придумать друг для друга задания, связанные с вашими общими моментами.",
        "tags": ["Для нас двоих", "Личное"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "День без гаджетов",
        "description": "Устроить цифровой детокс: только вы, разговоры и тёплый чай.",
        "tags": ["Личное", "Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Пикник на крыше",
        "description": "Найти видовую точку, взять плед и устроить там маленькое свидание.",
        "tags": ["Для нас двоих", "Большая мечта"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Свидание в музее",
        "description": "Выбрать зал, который вы оба любите, и поделиться впечатлениями.",
        "tags": ["Для нас двоих"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Домашний спа-день",
        "description": "Аромасвечи, маски, расслабляющая музыка и массаж друг другу.",
        "tags": ["Личное", "Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Обмен книгами",
        "description": "Выбрать по одной книге друг для друга и обсудить через неделю.",
        "tags": ["Личное"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Прогулка по крышам воспоминаний",
        "description": "Пройтись по местам, где вы уже были вместе, и вспомнить детали.",
        "tags": ["Личное", "Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Танцы на кухне",
        "description": "Включить любимую песню и потанцевать прямо между шкафчиками.",
        "tags": ["Спонтанно", "Для нас двоих"],
        "default_horizon": "⚡ Прямо сейчас",
    },
    {
        "title": "Карточки комплиментов",
        "description": "Подготовить по 5 карточек, где написано за что вы любите партнёра.",
        "tags": ["Личное", "Подарок"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Секретный подарок",
        "description": "Каждый выбирает маленький сюрприз и дарит без повода.",
        "tags": ["Подарок", "Спонтанно"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Запустить семейный влог",
        "description": "Снять короткий ролик о том, как проходит ваш день вместе.",
        "tags": ["Для нас двоих", "Большая мечта"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Вечер настольного кулинарного шоу",
        "description": "Каждый готовит блюдо на время и презентует другому.",
        "tags": ["Для нас двоих"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Персональный гид",
        "description": "Показать партнёру свои любимые места в городе как туристу.",
        "tags": ["Для нас двоих", "Спонтанно"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Нарисовать общий герб",
        "description": "Придумать символ вашей пары и оформить его красиво.",
        "tags": ["Большая мечта", "Личное"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "День пледа и фильмов",
        "description": "Выбрать пять уютных фильмов и не выходить из-под пледа весь день.",
        "tags": ["Для нас двоих"],
        "default_horizon": "⏳ Когда-нибудь",
    },
    {
        "title": "Фестиваль домашних супов",
        "description": "Сварить по одному необычному супу и устроить дегустацию.",
        "tags": ["Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Общая копилка мечты",
        "description": "Начать банку, куда будете класть по символической сумме для большого желания.",
        "tags": ["Большая мечта"],
        "default_horizon": "⏳ Когда-нибудь",
    },
    {
        "title": "Урок танцев онлайн",
        "description": "Найти урок по танцу и попробовать повторить движения дома.",
        "tags": ["Для нас двоих", "Спонтанно"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Вечер поэзии",
        "description": "Читать друг другу любимые стихи или писать свои.",
        "tags": ["Личное"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Пикник на полу",
        "description": "Разложить еду прямо на ковре, зажечь свечи и слушать музыку.",
        "tags": ["Для нас двоих", "Спонтанно"],
        "default_horizon": "⚡ Прямо сейчас",
    },
    {
        "title": "Дегустация мороженого",
        "description": "Купить пять разных вкусов и выбрать любимый.",
        "tags": ["Спонтанно", "Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Совместный фотоальбом",
        "description": "Отобрать лучшие снимки и распечатать в мини-альбом.",
        "tags": ["Личное", "Подарок"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Медленное утро",
        "description": "Выходной без будильников, медленный завтрак и разговоры.",
        "tags": ["Личное"],
        "default_horizon": "⚡ Прямо сейчас",
    },
    {
        "title": "Сделать добро вместе",
        "description": "Выбрать благотворительный проект и помочь ему вдвоём.",
        "tags": ["Для нас двоих", "Большая мечта"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Собрать пазл",
        "description": "Выбрать красивую картинку и собирать её вечерами.",
        "tags": ["Для нас двоих"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Поход в караоке",
        "description": "Спеть дуэтом любимую песню, даже если стесняетесь.",
        "tags": ["Спонтанно", "Для нас двоих"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Список маленьких радостей",
        "description": "Записать 30 вещей, которые делают вас счастливыми, и исполнить одну.",
        "tags": ["Личное", "Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Ночной велопробег",
        "description": "Покататься на велосипедах по ночному городу.",
        "tags": ["Для нас двоих", "Спонтанно"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Совместный мини-курc",
        "description": "Пройти онлайн-урок по рисованию или фотографии.",
        "tags": ["Для нас двоих", "Большая мечта"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "День комплиментов",
        "description": "Целый день говорить друг другу тёплые слова при каждом поводе.",
        "tags": ["Личное"],
        "default_horizon": "⚡ Прямо сейчас",
    },
    {
        "title": "Записать подкаст",
        "description": "Обсудить на диктофон одну важную тему и переслушать через год.",
        "tags": ["Для нас двоих", "Большая мечта"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Посадить растение",
        "description": "Выбрать комнатное растение и ухаживать за ним вместе.",
        "tags": ["Для нас двоих", "Большая мечта"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Собрать коробку воспоминаний",
        "description": "Сложить туда билеты, открытки и маленькие символы ваших встреч.",
        "tags": ["Личное", "Подарок"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Устроить фотоквест",
        "description": "Составить список объектов и найти их в городе, делая снимки.",
        "tags": ["Спонтанно", "Для нас двоих"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Полёт на воздушном шаре",
        "description": "Крупная мечта для особого дня — запланировать заранее.",
        "tags": ["Большая мечта"],
        "default_horizon": "⏳ Когда-нибудь",
    },
    {
        "title": "День без расходов",
        "description": "Проверить, сколько радости можно придумать бесплатно.",
        "tags": ["Для нас двоих", "Спонтанно"],
        "default_horizon": "⚡ Прямо сейчас",
    },
    {
        "title": "Домашний бариста",
        "description": "Попробовать приготовить авторский кофе друг для друга.",
        "tags": ["Подарок", "Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Совместная медитация",
        "description": "Поставить таймер на 10 минут и помолчать вместе, держась за руки.",
        "tags": ["Личное", "Для нас двоих"],
        "default_horizon": "⚡ Прямо сейчас",
    },
    {
        "title": "Фестиваль домашнего кино",
        "description": "Снять короткий ролик за день и посмотреть вечером на экране.",
        "tags": ["Для нас двоих", "Большая мечта"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Катание на коньках",
        "description": "Собраться на каток и учить друг друга поддержкам.",
        "tags": ["Для нас двоих"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Вечер свечей и откровений",
        "description": "Ответить по очереди на 36 вопросов для близости.",
        "tags": ["Личное", "Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Совместная карта города",
        "description": "Отметить места, где вы уже были, и куда ещё хотите попасть.",
        "tags": ["Большая мечта", "Для нас двоих"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Полететь на выходные",
        "description": "Выбрать город мечты и запланировать короткое путешествие.",
        "tags": ["Большая мечта", "Для нас двоих"],
        "default_horizon": "⏳ Когда-нибудь",
    },
    {
        "title": "Собрать семейный рецепт",
        "description": "Позвонить родным, записать любимый рецепт и приготовить его.",
        "tags": ["Подарок", "Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Подушка путешествий",
        "description": "Сшить или заказать подушку с картой мест, где вы были вместе.",
        "tags": ["Подарок", "Большая мечта"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Видеописьмо детям из будущего",
        "description": "Записать тёплое обращение, которое посмотрите через много лет.",
        "tags": ["Большая мечта", "Личное"],
        "default_horizon": "⏳ Когда-нибудь",
    },
    {
        "title": "Собраться на рассвет",
        "description": "Встать до солнца, взять термос и встретить новый день вместе.",
        "tags": ["Для нас двоих", "Спонтанно"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Марафон обнимашек",
        "description": "Каждый час напоминать себе остановиться и обняться.",
        "tags": ["Личное", "Спонтанно"],
        "default_horizon": "⚡ Прямо сейчас",
    },
    {
        "title": "Сделать общий плейлист воспоминаний",
        "description": "Для каждого важного события выбрать песню и сохранить её.",
        "tags": ["Личное", "Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Запустить семейную традицию",
        "description": "Придумать ритуал, который будет повторяться каждый месяц.",
        "tags": ["Большая мечта", "Для нас двоих"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Испечь сердечный торт",
        "description": "Испечь торт в форме сердца и украсить его вместе.",
        "tags": ["Подарок", "Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Собрать капсулу времени",
        "description": "Сложить символы уходящего года и открыть через пять лет.",
        "tags": ["Большая мечта"],
        "default_horizon": "⏳ Когда-нибудь",
    },
    {
        "title": "Вечер настольных вопросов",
        "description": "Купить или придумать карточки вопросов и говорить по душам.",
        "tags": ["Личное", "Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
    {
        "title": "Домашняя фотобудка",
        "description": "Повесить фон, поставить штатив и устроить съёмку с таймером.",
        "tags": ["Для нас двоих", "Спонтанно"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Нарисовать мечту",
        "description": "Сделать рисунок или схему большого желания и повесить на видное место.",
        "tags": ["Большая мечта"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Снять комнату в отеле",
        "description": "Устроить мини-путешествие в собственном городе на одну ночь.",
        "tags": ["Для нас двоих", "Подарок"],
        "default_horizon": "📅 Этот год",
    },
    {
        "title": "Обмен мечтами",
        "description": "Каждый делится тремя заветными мечтами и выбираете одну общую.",
        "tags": ["Большая мечта", "Для нас двоих"],
        "default_horizon": "📆 Этот месяц",
    },
]


def _format_tags(tags: Optional[str]) -> str:
    if not tags:
        return "—"
    readable = ", ".join(tags_from_csv(tags))
    return readable or "—"


def format_wish_caption(wish: Wish) -> str:
    lines = [f"<b>{html.escape(wish.title)}</b>"]
    horizon = wish.time_horizon or "Без срока"
    if wish.due_date:
        horizon = f"{horizon} — {wish.due_date.isoformat()}"
    lines.append(f"⏰ {html.escape(horizon)}")

    if wish.price_flag:
        amount = wish.price_amount.strip() if wish.price_amount else "Идея бюджета есть"
        lines.append(f"💰 {html.escape(amount)}")
    else:
        lines.append("💰 Без бюджета")

    if wish.tags:
        lines.append(f"🏷 {html.escape(_format_tags(wish.tags))}")
    else:
        lines.append("🏷 Без тегов")

    author = wish.user_username or wish.user_first_name or "кто-то из вас"
    lines.append(f"🙋 {html.escape(author)}")
    status = "✅ Выполнено" if wish.status == "done" else "✨ В процессе"
    lines.append(status)
    return "\n".join(lines)


def build_summary_text(summary: Dict[str, object]) -> str:
    lines = ["<b>Сводка по желаниям</b>"]
    total_open = int(summary.get("total_open", 0))
    lines.append(f"Открыто: <b>{total_open}</b>")

    by_horizon: Dict[str, int] = summary.get("by_horizon", {}) or {}
    if by_horizon:
        parts = [f"{html.escape(name)} — {count}" for name, count in by_horizon.items()]
        lines.append("По срокам: " + ", ".join(parts))
    else:
        lines.append("По срокам: пока без отметок.")

    nearest: Optional[Wish] = summary.get("nearest")  # type: ignore[assignment]
    if nearest and nearest.due_date:
        lines.append(
            f"Ближайшее: <b>{html.escape(nearest.title)}</b> — {nearest.due_date.isoformat()}"
        )
    elif nearest:
        horizon = nearest.time_horizon or "без срока"
        lines.append(
            f"Ближайшее: <b>{html.escape(nearest.title)}</b> — {html.escape(horizon)}"
        )
    else:
        lines.append("Ближайшее: пока нет точных дат.")

    random_wish: Optional[Wish] = summary.get("random")  # type: ignore[assignment]
    if random_wish:
        lines.append(f"Случайная открытая идея: <b>{html.escape(random_wish.title)}</b>")
    else:
        lines.append("Случайная открытая идея: добавьте хотя бы одну мечту 💛")

    motivation = summary.get("motivation")
    if motivation:
        lines.append(f"Мотивашка: {html.escape(str(motivation))}")

    return "\n".join(lines)


def parse_price(text: str) -> object:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Сумма не должна быть пустой.")
    normalized = cleaned.replace(" ", "").replace(",", ".")
    try:
        value = float(normalized)
    except ValueError:
        return cleaned
    if value.is_integer():
        return int(value)
    return round(value, 2)


def parse_due_date(text: str) -> date:
    cleaned = text.strip()
    try:
        parts = cleaned.split("-")
        if len(parts) != 3:
            raise ValueError
        year, month, day = map(int, parts)
        return date(year, month, day)
    except Exception as exc:  # pragma: no cover - simple validation
        raise ValueError("Дата должна быть в формате YYYY-MM-DD, например 2024-02-14.") from exc


def toggle_tag(csv: Optional[str], tag: str) -> str:
    tags = tags_from_csv(csv)
    if tag in tags:
        tags.remove(tag)
    else:
        tags.append(tag)
    return ",".join(dict.fromkeys(tags))


def tags_from_csv(csv: Optional[str]) -> List[str]:
    if not csv:
        return []
    return [part.strip() for part in csv.split(",") if part.strip()]


def format_random_idea(idea: Dict[str, object]) -> str:
    title = html.escape(str(idea["title"]))
    description = html.escape(str(idea["description"]))
    tags = ", ".join(idea.get("tags", []))
    horizon = idea.get("default_horizon", "⏳ Когда-нибудь")
    lines = [f"<b>{title}</b>", description]
    if tags:
        lines.append(f"🏷 {html.escape(tags)}")
    lines.append(f"⏰ {html.escape(str(horizon))}")
    return "\n".join(lines)


def format_draft_price(flag: Optional[bool], amount: Optional[str]) -> str:
    if flag is None:
        return "Не указано"
    if not flag:
        return "Нет"
    if amount:
        return amount
    return "Есть"


def format_draft_time(time_horizon: Optional[str], due: Optional[date]) -> str:
    if due:
        return f"🗓 {due.isoformat()}"
    if time_horizon:
        return time_horizon
    return "Не выбрано"

