import os
from datetime import datetime, timedelta

from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.database import async_session
from bot.keyboards import get_categories_inline_keyboard, get_main_reply_keyboard, get_subtopics_inline_keyboard
from bot.llm import get_llm_response
from bot.models import Category, Feedback, LLMConfig, LLMRequest, LLMUsage, Log, Subtopic, User

# Простой in‑memory rate limiting (5 запросов в минуту)
user_requests = {}
RATE_LIMIT = 20  # запросов в минуту
SUPERUSER_TG_ID = os.getenv("SUPERUSER_TG_ID")  # Суперпользовательский TG id из .env
SUPERUSER_TG_NICK = os.getenv("SUPERUSER_TG_NICK")  # Суперпользовательский TG Nick из .env
SUPERUSER_TG_NAME = os.getenv("SUPERUSER_TG_NAME")  # Имя суперпользователя


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
    welcome_text = "<b>Добро пожаловать!</b>\n" "Выберите категорию."
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
        f"Докладчик: <a href='https://t.me/{SUPERUSER_TG_NICK}'>{SUPERUSER_TG_NAME}</a>.\n"
        "Тема: <b>Использовании LLM в учебе, работе и жизни</b>.\n"
        "Здесь вы можете подробнее познакомиться с рассказанными примерами и источниками.\n\n"
        f"<b>Также вам доступно несколько обращений к GPT, обращение происходит к {os.getenv('LLM_API_MODEL')}</b>.\n\n"
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
    else:
        await llm_query_handler(update, context)


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
        result = await session.execute(
            select(Subtopic).options(joinedload(Subtopic.category)).where(Subtopic.id == subtopic_id)
        )
        subtopic = result.scalar_one_or_none()
        if subtopic:
            log = Log(user_id=str(user_id), message=f"Selected subtopic: {subtopic.name}")
            session.add(log)
            await session.commit()
            category_name = subtopic.category.name if subtopic.category else "Неизвестная категория"
            header = f"Вы выбрали категорию: <b>{category_name}</b>\nРаздел: <b>{subtopic.name}</b>\n\n"
            content = subtopic.content if subtopic.content else "Нет дополнительной информации."
            final_text = header + content
            await query.message.edit_text(final_text, parse_mode="HTML")
            if subtopic.media:
                if subtopic.media.endswith(".mp4"):
                    await query.message.reply_video(video=subtopic.media)
                else:
                    await query.message.reply_animation(animation=subtopic.media)
        else:
            await query.message.reply_text("Подтема не найдена.", parse_mode="HTML")


# Новый обработчик для LLM-запросов (если пользователь просто пишет боту)
async def llm_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await register_user(update, context)  # Автоматическая регистрация пользователя
    if not await check_rate_limit(user_id):
        await update.message.reply_text("Слишком много запросов. Пожалуйста, подождите.")
        return

    prompt = update.message.text

    # Проверка, включена ли LLM-функциональность
    async with async_session() as session:
        config_result = await session.execute(select(LLMConfig))
        config = config_result.scalars().first()
        if config is None or not config.enabled:
            await update.message.reply_text("LLM функция временно отключена.")
            return

        # Получаем или создаём запись с лимитом для пользователя
        result = await session.execute(select(LLMUsage).where(LLMUsage.user_id == str(user_id)))
        usage = result.scalar_one_or_none()
        if usage is None:
            usage = LLMUsage(user_id=str(user_id), used=0, limit=int(os.getenv("DEFAULT_LIMIT_LLM")))
            session.add(usage)
            await session.commit()
        if usage.used >= usage.limit:
            await update.message.reply_text(
                f"Вы исчерпали лимит запросов. Для увеличения обратитесь к @{SUPERUSER_TG_NICK}",
                reply_to_message_id=update.message.message_id,
            )
            return

    # Получаем ответ от LLM
    try:
        response_text = await get_llm_response(prompt)
    except Exception as e:
        async with async_session() as session:
            log = Log(user_id=str(user_id), message=f"Ошибка при обращении к LLM API. User:{user_id}, Error:{e}")
            session.add(log)
            await session.commit()
        await update.message.reply_text(
            "Ошибка при обращении к LLM API.",
            reply_to_message_id=update.message.message_id,
        )
        return

    # Сохраняем запрос и ответ в БД и увеличиваем счётчик использования
    async with async_session() as session:
        llm_req = LLMRequest(user_id=str(user_id), prompt=prompt, response=response_text)
        session.add(llm_req)
        # Обновляем лимит
        result = await session.execute(select(LLMUsage).where(LLMUsage.user_id == str(user_id)))
        usage = result.scalar_one_or_none()
        if usage:
            usage.used += 1
        await session.commit()

    await update.message.reply_text(
        response_text,
        parse_mode="HTML",
        reply_to_message_id=update.message.message_id,
    )


# Обработчики для суперпользовательских команд


async def llm_enable_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != SUPERUSER_TG_ID:
        await update.message.reply_text(
            "У вас нет прав для выполнения этой команды.",
            reply_to_message_id=update.message.message_id,
        )
        return
    async with async_session() as session:
        result = await session.execute(select(LLMConfig))
        config = result.scalars().first()
        if config is None:
            config = LLMConfig(enabled=True)
            session.add(config)
        else:
            config.enabled = True
        await session.commit()
    await update.message.reply_text(
        "LLM функция включена.",
        reply_to_message_id=update.message.message_id,
    )


async def llm_disable_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != SUPERUSER_TG_ID:
        await update.message.reply_text(
            "У вас нет прав для выполнения этой команды.",
            reply_to_message_id=update.message.message_id,
        )
        return
    async with async_session() as session:
        result = await session.execute(select(LLMConfig))
        config = result.scalars().first()
        if config is None:
            config = LLMConfig(enabled=False)
            session.add(config)
        else:
            config.enabled = False
        await session.commit()
    await update.message.reply_text(
        "LLM функция отключена.",
        reply_to_message_id=update.message.message_id,
    )


async def llm_set_limit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != SUPERUSER_TG_ID:
        await update.message.reply_text(
            "У вас нет прав для выполнения этой команды.",
            reply_to_message_id=update.message.message_id,
        )
        return
    try:
        target = context.args[0]
        new_limit = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Используйте: /llm_set_limit <tg_id или @username> <новый_лимит>",
            reply_to_message_id=update.message.message_id,
        )
        return
    target_tg_id = None
    if target.startswith("@"):
        # Если указан ник, ищем пользователя по username
        async with async_session() as session:
            result = await session.execute(select(User).where(User.username == target[1:]))
            user_obj = result.scalar_one_or_none()
            if user_obj:
                target_tg_id = user_obj.tg_id
            else:
                await update.message.reply_text(
                    "Пользователь с таким ником не найден.",
                    reply_to_message_id=update.message.message_id,
                )
                return
    else:
        target_tg_id = target
    async with async_session() as session:
        result = await session.execute(select(LLMUsage).where(LLMUsage.user_id == str(target_tg_id)))
        usage = result.scalar_one_or_none()
        if usage is None:
            usage = LLMUsage(user_id=str(target_tg_id), used=0, limit=new_limit)
            session.add(usage)
        else:
            usage.limit = new_limit
        await session.commit()
    await update.message.reply_text(
        f"Лимит для пользователя {target} установлен в {new_limit}.",
        reply_to_message_id=update.message.message_id,
    )


def register_handlers(app):
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("about", about_handler))
    app.add_handler(CommandHandler("feedback", feedback_command_handler))
    app.add_handler(CommandHandler("llm_enable", llm_enable_handler))
    app.add_handler(CommandHandler("llm_disable", llm_disable_handler))
    app.add_handler(CommandHandler("llm_set_limit", llm_set_limit_handler))
    app.add_handler(CallbackQueryHandler(category_callback, pattern=r"^category:"))
    app.add_handler(CallbackQueryHandler(back_to_categories_callback, pattern=r"^back_to_categories$"))
    app.add_handler(CallbackQueryHandler(subtopic_callback, pattern=r"^subtopic:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler), group=1)
