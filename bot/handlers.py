import asyncio
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from sqlalchemy.future import select

from bot.database import async_session
from bot.models import Category, Subtopic, Feedback, Log, User
from bot.keyboards import get_categories_inline_keyboard, get_subtopics_inline_keyboard, get_main_reply_keyboard

# Простой in‑memory rate limiting (5 запросов в минуту)
user_requests = {}
RATE_LIMIT = 5  # запросов в минуту


async def check_rate_limit(user_id: int) -> bool:
    now = datetime.utcnow()
    uid = str(user_id)
    if uid not in user_requests:
        user_requests[uid] = []
    user_requests[uid] = [ts for ts in user_requests[uid] if now - ts < timedelta(minutes=1)]
    if len(user_requests[uid]) >= RATE_LIMIT:
        return False
    user_requests[uid].append(now)
    return True


async def register_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tg_id = str(user.id)
    full_name = user.first_name + (" " + user.last_name if user.last_name else "")
    username = user.username
    phone = None  # Телефон не передаётся автоматически
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        existing_user = result.scalar_one_or_none()
        if not existing_user:
            new_user = User(tg_id=tg_id, full_name=full_name, phone=phone, username=username)
            session.add(new_user)
            await session.commit()


# Обработчик команды /start
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await register_user(update, context)
    if not await check_rate_limit(user_id):
        await update.message.reply_text("Слишком много запросов. Пожалуйста, подождите.")
        return

    main_keyboard = get_main_reply_keyboard()
    welcome_text = "<b>Добро пожаловать!</b>\n" "Выберите категорию для изучения тем конференции <i>Войти в IT</i>."
    # Отправляем приветственное сообщение с постоянной клавиатурой
    await update.message.reply_text(welcome_text, reply_markup=main_keyboard, parse_mode="HTML")
    # Отправляем inline‑клавиатуру с категориями
    inline_kb = await get_categories_inline_keyboard()
    await update.message.reply_text("Выберите категорию:", reply_markup=inline_kb, parse_mode="HTML")

    async with async_session() as session:
        log = Log(user_id=str(user_id), message="/start")
        session.add(log)
        await session.commit()


# Обработчик команды /about
async def about_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    about_text = (
        "<b>О боте</b>\n"
        "Этот бот был создан для конференции <i>Войти в IT</i> "
        "для доклада <a href='https://t.me/NiKoV_HET'>Овчинникова Никиты</a>.\n"
        "Доклад на тему <b>Использовании LLM в учебе, работе и жизни</b>.\n"
        "Здесь вы можете подробнее познакомиться с рассказанными примерами и источниками.\n"
        "Исходный код бота доступен на <a href='https://github.com/NiKoV-HET/VoitiVIT_LLM_bot'>GitHub</a>"
    )
    await update.message.reply_text(about_text, parse_mode="HTML")


# Обработчик команды /feedback
async def feedback_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пожалуйста, введите ваш отзыв:")
    context.user_data["awaiting_feedback"] = True


# Обработчик текстовых сообщений (обработка постоянной клавиатуры и обратной связи)
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_rate_limit(user_id):
        await update.message.reply_text("Слишком много запросов. Пожалуйста, подождите.")
        return

    text = update.message.text

    # Если пользователь нажал кнопку "Основное меню"
    if text == "Основное меню":
        inline_kb = await get_categories_inline_keyboard()
        await update.message.reply_text("Выберите категорию:", reply_markup=inline_kb, parse_mode="HTML")
        return

    if text == "О боте":
        await about_handler(update, context)
        return

    if text == "Оставить обратную связь":
        await feedback_command_handler(update, context)
        return

    # Если бот ожидает отзыв
    if context.user_data.get("awaiting_feedback"):
        feedback_text = text
        async with async_session() as session:
            feedback = Feedback(user_id=str(user_id), message=feedback_text)
            session.add(feedback)
            await session.commit()
        await update.message.reply_text("Спасибо за ваш отзыв!", parse_mode="HTML")
        async with async_session() as session:
            log = Log(user_id=str(user_id), message=f"Feedback: {feedback_text}")
            session.add(log)
            await session.commit()
        context.user_data["awaiting_feedback"] = False
        return


# Callback‑обработчик для выбора категории
async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        category_id = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        await query.message.reply_text("Неверные данные категории.", parse_mode="HTML")
        return
    async with async_session() as session:
        result = await session.execute(select(Category).where(Category.id == category_id))
        category = result.scalar_one_or_none()
        if not category:
            await query.message.reply_text("Категория не найдена.", parse_mode="HTML")
            return
    # Получаем inline‑клавиатуру с подкатегориями и добавляем кнопку "Назад"
    inline_kb = await get_subtopics_inline_keyboard(category_id)
    text = f"<b>Вы выбрали категорию</b> «{category.name}». <i>Выберите подтему:</i>"
    await query.message.edit_text(text, reply_markup=inline_kb, parse_mode="HTML")


# Callback‑обработчик для возврата к списку категорий
async def back_to_categories_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    inline_kb = await get_categories_inline_keyboard()
    await query.message.edit_text("<b>Выберите категорию:</b>", reply_markup=inline_kb, parse_mode="HTML")


# Callback‑обработчик для выбора подтемы
async def subtopic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not await check_rate_limit(user_id):
        await query.message.reply_text("Слишком много запросов. Пожалуйста, подождите.", parse_mode="HTML")
        return
    try:
        subtopic_id = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        await query.message.reply_text("Неверные данные.", parse_mode="HTML")
        return
    async with async_session() as session:
        result = await session.execute(select(Subtopic).where(Subtopic.id == subtopic_id))
        subtopic = result.scalar_one_or_none()
        if subtopic:
            log = Log(user_id=str(user_id), message=f"Selected subtopic: {subtopic.name}")
            session.add(log)
            await session.commit()
            text = subtopic.content if subtopic.content else "Нет дополнительной информации."
            await query.message.edit_text(text, parse_mode="HTML")
            if subtopic.media:
                if subtopic.media.endswith(".mp4"):
                    await query.message.reply_video(video=subtopic.media)
                else:
                    await query.message.reply_animation(animation=subtopic.media)
        else:
            await query.message.reply_text("Подтема не найдена.", parse_mode="HTML")


def register_handlers(app):
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("about", about_handler))
    app.add_handler(CommandHandler("feedback", feedback_command_handler))
    app.add_handler(CallbackQueryHandler(category_callback, pattern=r"^category:"))
    app.add_handler(CallbackQueryHandler(back_to_categories_callback, pattern=r"^back_to_categories$"))
    app.add_handler(CallbackQueryHandler(subtopic_callback, pattern=r"^subtopic:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
