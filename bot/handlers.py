from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from sqlalchemy.future import select

from bot.database import async_session
from bot.models import Category, Subtopic, Feedback, Log
from bot.keyboards import get_main_menu_keyboard, get_subtopics_keyboard

# Простой in-memory rate limiting (5 запросов в минуту)
user_requests = {}
RATE_LIMIT = 5  # запросов в минуту


async def check_rate_limit(user_id: int) -> bool:
    now = datetime.utcnow()
    uid = str(user_id)
    if uid not in user_requests:
        user_requests[uid] = []
    # Оставляем только запросы за последние 60 секунд
    user_requests[uid] = [ts for ts in user_requests[uid] if now - ts < timedelta(minutes=1)]
    if len(user_requests[uid]) >= RATE_LIMIT:
        return False
    user_requests[uid].append(now)
    return True


# Обработчик команды /start
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_rate_limit(user_id):
        await update.message.reply_text("Слишком много запросов. Пожалуйста, подождите.")
        return

    keyboard = await get_main_menu_keyboard()
    await update.message.reply_text("Добро пожаловать! Выберите категорию:", reply_markup=keyboard)

    # Логирование запроса
    async with async_session() as session:
        log = Log(user_id=str(user_id), message="/start")
        session.add(log)
        await session.commit()


# Обработчик текстовых сообщений (выбор категории и сбор обратной связи)
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_rate_limit(user_id):
        await update.message.reply_text("Слишком много запросов. Пожалуйста, подождите.")
        return

    text = update.message.text

    # Если пользователь выбрал "Оставить обратную связь"
    if text == "Оставить обратную связь":
        await update.message.reply_text("Пожалуйста, введите ваш отзыв:")
        context.user_data["awaiting_feedback"] = True
        return

    # Если бот ожидает отзыв от пользователя
    if context.user_data.get("awaiting_feedback"):
        feedback_text = text
        async with async_session() as session:
            feedback = Feedback(user_id=str(user_id), message=feedback_text)
            session.add(feedback)
            await session.commit()
        await update.message.reply_text("Спасибо за ваш отзыв!")
        async with async_session() as session:
            log = Log(user_id=str(user_id), message=f"Feedback: {feedback_text}")
            session.add(log)
            await session.commit()
        context.user_data["awaiting_feedback"] = False
        return

    # Иначе обрабатываем выбор категории
    async with async_session() as session:
        result = await session.execute(select(Category).where(Category.name == text))
        category = result.scalar_one_or_none()
        if category:
            log = Log(user_id=str(user_id), message=f"Selected category: {text}")
            session.add(log)
            await session.commit()

            # Проверяем наличие подтем для выбранной категории
            result = await session.execute(select(Subtopic).where(Subtopic.category_id == category.id))
            subtopics = result.scalars().all()
            if subtopics:
                keyboard = await get_subtopics_keyboard(category.name)
                await update.message.reply_text(
                    f"Вы выбрали категорию «{category.name}». Выберите подтему:", reply_markup=keyboard
                )
            else:
                content = category.description if category.description else "Информация по данной теме отсутствует."
                await update.message.reply_text(content)
        else:
            await update.message.reply_text("Неизвестная команда. Пожалуйста, используйте клавиатуру.")


# Обработчик callback-запросов для выбора подтемы
async def subtopic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Подтверждаем получение callback
    user_id = query.from_user.id
    if not await check_rate_limit(user_id):
        await query.message.reply_text("Слишком много запросов. Пожалуйста, подождите.")
        return

    try:
        subtopic_id = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        await query.message.reply_text("Неверные данные.")
        return

    async with async_session() as session:
        result = await session.execute(select(Subtopic).where(Subtopic.id == subtopic_id))
        subtopic = result.scalar_one_or_none()
        if subtopic:
            log = Log(user_id=str(user_id), message=f"Selected subtopic: {subtopic.name}")
            session.add(log)
            await session.commit()

            text = subtopic.content if subtopic.content else "Нет дополнительной информации."
            await query.message.reply_text(text)
            if subtopic.media:
                if subtopic.media.endswith(".mp4"):
                    await query.message.reply_video(video=subtopic.media)
                else:
                    await query.message.reply_animation(animation=subtopic.media)
        else:
            await query.message.reply_text("Подтема не найдена.")


def register_handlers(app):
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(subtopic_callback, pattern=r"^subtopic:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
