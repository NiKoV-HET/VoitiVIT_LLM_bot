import os
from datetime import datetime, timedelta

from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.database import async_session
from bot.keyboards import get_admin_control_keyboard, get_admin_reply_keyboard, get_categories_inline_keyboard, get_main_reply_keyboard, get_subtopics_inline_keyboard, get_users_keyboard, get_user_actions_keyboard, get_llm_models_keyboard
from bot.llm import get_llm_response
from bot.models import Category, Feedback, LLMConfig, LLMRequest, LLMUsage, Log, Subtopic, User, UserImage, LLMModel
from bot.storage import image_to_base64, save_image

# Простой in‑memory rate limiting (5 запросов в минуту)
user_requests = {}
RATE_LIMIT = 20  # запросов в минуту
SUPERUSER_TG_ID = os.getenv("SUPERUSER_TG_ID")  # Суперпользовательский TG id из .env
SUPERUSER_TG_NICK = os.getenv("SUPERUSER_TG_NICK")  # Суперпользовательский TG Nick из .env
SUPERUSER_TG_NAME = os.getenv("SUPERUSER_TG_NAME")  # Имя суперпользователя

# Словарь для хранения последних загруженных изображений пользователей
user_last_image = {}

# Словарь для хранения текущей страницы пользователей для каждого администратора
admin_user_pages = {}

# Словарь для хранения выбранного пользователя для каждого администратора
selected_users = {}


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
            new_user = User(
                tg_id=tg_id, 
                full_name=full_name, 
                phone=phone, 
                username=username,
                llm_model=os.getenv("LLM_API_MODEL"),  # Устанавливаем модель по умолчанию
                llm_enabled=True  # По умолчанию LLM включен для пользователя
            )
            session.add(new_user)
            await session.commit()


# Обработчик команды /start
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await register_user(update, context)
    if not await check_rate_limit(user_id):
        await update.message.reply_text("Слишком много запросов. Пожалуйста, подождите.")
        return

    # Проверяем, является ли пользователь суперпользователем
    is_superuser = str(user_id) == SUPERUSER_TG_ID
    
    # Выбираем соответствующую клавиатуру
    if is_superuser:
        main_keyboard = get_admin_reply_keyboard()
    else:
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
    user_id = update.effective_user.id
    
    # Получаем информацию о модели LLM пользователя
    llm_model_info = ""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == str(user_id)))
        user = result.scalar_one_or_none()
        if user:
            model_name = user.llm_model if user.llm_model else os.getenv('LLM_API_MODEL')
            llm_enabled = "включена" if user.llm_enabled else "отключена"
            
            # Получаем информацию о глобальном состоянии LLM
            config_result = await session.execute(select(LLMConfig))
            config = config_result.scalars().first()
            global_enabled = config is not None and config.enabled
            
            # Получаем информацию о лимите запросов
            usage_result = await session.execute(select(LLMUsage).where(LLMUsage.user_id == str(user_id)))
            usage = usage_result.scalar_one_or_none()
            limit_info = ""
            if usage:
                limit_info = f"Использовано {usage.used} из {usage.limit} запросов."
            
            llm_model_info = f"\n\n<b>Ваша модель LLM:</b> {model_name}\n"
            llm_model_info += f"<b>Статус LLM для вас:</b> {llm_enabled}\n"
            llm_model_info += f"<b>Глобальный статус LLM:</b> {'включена' if global_enabled else 'отключена'}\n"
            if limit_info:
                llm_model_info += f"<b>{limit_info}</b>"
    
    about_text = (
        "<b>О боте</b>\n"
        "Этот бот был создан для конференции <i>Войти в IT</i> "
        f"Докладчик: <a href='https://t.me/{SUPERUSER_TG_NICK}'>{SUPERUSER_TG_NAME}</a>.\n"
        "Тема: <b>Использовании LLM в учебе, работе и жизни</b>.\n"
        "Здесь вы можете подробнее познакомиться с рассказанными примерами и источниками.\n\n"
        f"<b>Также вам доступно несколько обращений к GPT.</b>{llm_model_info}\n\n"
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
    is_superuser = str(user_id) == SUPERUSER_TG_ID

    # Если бот ожидает отзыв - обрабатываем его в первую очередь
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
        
    # Обработка кнопок администратора
    if is_superuser:
        # Кнопка "Управление ботом"
        if text == "Управление ботом":
            admin_keyboard = get_admin_control_keyboard()
            await update.message.reply_text(
                "Панель управления ботом. Выберите действие:", 
                reply_markup=admin_keyboard
            )
            return
            
        # Кнопка "Назад" в меню управления
        if text == "Назад":
            admin_keyboard = get_admin_reply_keyboard()
            await update.message.reply_text(
                "Возврат в основное меню", 
                reply_markup=admin_keyboard
            )
            return
            
        # Кнопка "Управление пользователями"
        if text == "Управление пользователями":
            # Устанавливаем начальную страницу
            admin_user_pages[str(user_id)] = 0
            # Получаем клавиатуру с пользователями
            users_keyboard = await get_users_keyboard(page=0)
            await update.message.reply_text(
                "Выберите пользователя:", 
                reply_markup=users_keyboard
            )
            return
            
        # Кнопка "Вернуться в меню управления"
        if text == "Вернуться в меню управления":
            admin_keyboard = get_admin_control_keyboard()
            await update.message.reply_text(
                "Панель управления ботом. Выберите действие:", 
                reply_markup=admin_keyboard
            )
            return
            
        # Кнопка "Назад к списку пользователей"
        if text == "Назад к списку пользователей":
            # Получаем текущую страницу
            current_page = admin_user_pages.get(str(user_id), 0)
            # Очищаем выбранного пользователя
            if str(user_id) in selected_users:
                del selected_users[str(user_id)]
            # Получаем клавиатуру с пользователями
            users_keyboard = await get_users_keyboard(page=current_page)
            await update.message.reply_text(
                "Выберите пользователя:", 
                reply_markup=users_keyboard
            )
            return
            
        # Обработка навигации по страницам пользователей
        if text == "◀️ Назад":
            # Уменьшаем номер страницы
            current_page = admin_user_pages.get(str(user_id), 0)
            if current_page > 0:
                admin_user_pages[str(user_id)] = current_page - 1
            # Получаем клавиатуру с пользователями
            users_keyboard = await get_users_keyboard(page=admin_user_pages[str(user_id)])
            await update.message.reply_text(
                "Выберите пользователя:", 
                reply_markup=users_keyboard
            )
            return
            
        if text == "Вперед ▶️":
            # Увеличиваем номер страницы
            current_page = admin_user_pages.get(str(user_id), 0)
            admin_user_pages[str(user_id)] = current_page + 1
            # Получаем клавиатуру с пользователями
            users_keyboard = await get_users_keyboard(page=admin_user_pages[str(user_id)])
            await update.message.reply_text(
                "Выберите пользователя:", 
                reply_markup=users_keyboard
            )
            return
            
        # Проверяем, выбран ли пользователь из списка
        async with async_session() as session:
            users_result = await session.execute(select(User))
            users = users_result.scalars().all()
            
            for user_obj in users:
                display_name = f"{user_obj.full_name}"
                if user_obj.username:
                    display_name += f" (@{user_obj.username})"
                    
                if text == display_name:
                    # Сохраняем выбранного пользователя
                    selected_users[str(user_id)] = user_obj.tg_id
                    
                    # Получаем дополнительную информацию о пользователе
                    llm_status = "включен" if user_obj.llm_enabled else "отключен"
                    model_info = f"Модель: {user_obj.llm_model}" if user_obj.llm_model else "Модель не установлена"
                    
                    # Получаем информацию о лимите
                    usage_result = await session.execute(select(LLMUsage).where(LLMUsage.user_id == user_obj.tg_id))
                    usage = usage_result.scalar_one_or_none()
                    limit_info = ""
                    if usage:
                        limit_info = f"Использовано {usage.used} из {usage.limit} запросов"
                    else:
                        limit_info = "Лимит не установлен"
                    
                    # Показываем клавиатуру действий с пользователем
                    actions_keyboard = get_user_actions_keyboard()
                    await update.message.reply_text(
                        f"Выбран пользователь: {display_name}\n"
                        f"ID: {user_obj.tg_id}\n"
                        f"LLM: {llm_status}\n"
                        f"{model_info}\n"
                        f"{limit_info}\n\n"
                        f"Выберите действие:", 
                        reply_markup=actions_keyboard
                    )
                    return
        
        # Если выбран пользователь, обрабатываем действия с ним
        if str(user_id) in selected_users:
            selected_user_id = selected_users[str(user_id)]
            
            # Действие "Включить LLM"
            if text == "Включить LLM":
                async with async_session() as session:
                    result = await session.execute(select(User).where(User.tg_id == selected_user_id))
                    user_obj = result.scalar_one_or_none()
                    if user_obj:
                        user_obj.llm_enabled = True
                        await session.commit()
                        # Получаем обновленную информацию о пользователе
                        user_info = await get_user_info(selected_user_id)
                        await update.message.reply_text(f"LLM функция включена для пользователя.\n\n{user_info}")
                    else:
                        await update.message.reply_text("Пользователь не найден.")
                return
                
            # Действие "Выключить LLM"
            if text == "Выключить LLM":
                async with async_session() as session:
                    result = await session.execute(select(User).where(User.tg_id == selected_user_id))
                    user_obj = result.scalar_one_or_none()
                    if user_obj:
                        user_obj.llm_enabled = False
                        await session.commit()
                        # Получаем обновленную информацию о пользователе
                        user_info = await get_user_info(selected_user_id)
                        await update.message.reply_text(f"LLM функция отключена для пользователя.\n\n{user_info}")
                    else:
                        await update.message.reply_text("Пользователь не найден.")
                return
                
            # Действие "Установить модель"
            if text == "Установить модель":
                # Получаем клавиатуру с моделями
                models_keyboard = await get_llm_models_keyboard()
                await update.message.reply_text(
                    "Выберите модель для пользователя или добавьте новую:",
                    reply_markup=models_keyboard
                )
                context.user_data["awaiting_model_selection"] = True
                return
                
            # Действие "Установить лимит"
            if text == "Установить лимит":
                await update.message.reply_text(
                    "Введите новый лимит запросов для пользователя (число):"
                )
                context.user_data["awaiting_limit_for_user"] = True
                return
        
        # Обработка выбора модели из списка
        if context.user_data.get("awaiting_model_selection") and str(user_id) in selected_users:
            selected_user_id = selected_users[str(user_id)]
            
            # Если выбрана опция "Добавить новую модель"
            if text == "Добавить новую модель":
                await update.message.reply_text(
                    "Введите название новой модели (как оно будет использоваться в API):"
                )
                context.user_data["awaiting_new_model_name"] = True
                context.user_data["awaiting_model_selection"] = False
                return
                
            # Если выбрана опция "Назад"
            if text == "Назад":
                # Возвращаемся к действиям с пользователем
                actions_keyboard = get_user_actions_keyboard()
                await update.message.reply_text(
                    "Выберите действие:", 
                    reply_markup=actions_keyboard
                )
                context.user_data["awaiting_model_selection"] = False
                return
                
            # Проверяем, выбрана ли модель из списка
            async with async_session() as session:
                models_result = await session.execute(select(LLMModel))
                models = models_result.scalars().all()
                
                for model in models:
                    model_display = f"{model.name} - {model.description}"
                    if text == model_display:
                        # Устанавливаем выбранную модель для пользователя
                        result = await session.execute(select(User).where(User.tg_id == selected_user_id))
                        user_obj = result.scalar_one_or_none()
                        if user_obj:
                            user_obj.llm_model = model.name
                            await session.commit()
                            # Получаем обновленную информацию о пользователе
                            user_info = await get_user_info(selected_user_id)
                            await update.message.reply_text(
                                f"Модель LLM для пользователя установлена на {model.name}.\n\n{user_info}",
                                reply_markup=get_user_actions_keyboard()
                            )
                        else:
                            await update.message.reply_text("Пользователь не найден.")
                        
                        context.user_data["awaiting_model_selection"] = False
                        return
            
            # Если модель не найдена, сообщаем об ошибке
            await update.message.reply_text(
                "Выбранная модель не найдена. Пожалуйста, выберите модель из списка или добавьте новую.",
                reply_markup=await get_llm_models_keyboard()
            )
            return
            
        # Обработка ввода названия новой модели
        if context.user_data.get("awaiting_new_model_name"):
            model_name = text.strip()
            context.user_data["new_model_name"] = model_name
            context.user_data["awaiting_new_model_name"] = False
            context.user_data["awaiting_new_model_description"] = True
            
            await update.message.reply_text(
                f"Введите описание для модели '{model_name}':"
            )
            return
            
        # Обработка ввода описания новой модели
        if context.user_data.get("awaiting_new_model_description") and "new_model_name" in context.user_data:
            model_description = text.strip()
            model_name = context.user_data["new_model_name"]
            
            # Добавляем новую модель в базу данных
            async with async_session() as session:
                # Проверяем, существует ли уже такая модель
                result = await session.execute(select(LLMModel).where(LLMModel.name == model_name))
                existing_model = result.scalar_one_or_none()
                
                if existing_model:
                    await update.message.reply_text(
                        f"Модель с названием '{model_name}' уже существует. Пожалуйста, выберите другое название.",
                        reply_markup=await get_llm_models_keyboard()
                    )
                else:
                    # Создаем новую модель
                    new_model = LLMModel(name=model_name, description=model_description)
                    session.add(new_model)
                    await session.commit()
                    
                    # Если есть выбранный пользователь, устанавливаем ему эту модель
                    if str(user_id) in selected_users:
                        selected_user_id = selected_users[str(user_id)]
                        user_result = await session.execute(select(User).where(User.tg_id == selected_user_id))
                        user_obj = user_result.scalar_one_or_none()
                        
                        if user_obj:
                            user_obj.llm_model = model_name
                            await session.commit()
                            # Получаем обновленную информацию о пользователе
                            user_info = await get_user_info(selected_user_id)
                            await update.message.reply_text(
                                f"Новая модель '{model_name}' добавлена и установлена для пользователя.\n\n{user_info}",
                                reply_markup=get_user_actions_keyboard()
                            )
                        else:
                            await update.message.reply_text(
                                f"Новая модель '{model_name}' добавлена, но пользователь не найден.",
                                reply_markup=get_user_actions_keyboard()
                            )
            
            # Очищаем состояние
            context.user_data.pop("new_model_name", None)
            context.user_data["awaiting_new_model_description"] = False
            return
        
        # Обработка ввода лимита для пользователя
        if context.user_data.get("awaiting_limit_for_user") and str(user_id) in selected_users:
            selected_user_id = selected_users[str(user_id)]
            try:
                new_limit = int(text.strip())
                
                async with async_session() as session:
                    result = await session.execute(select(LLMUsage).where(LLMUsage.user_id == selected_user_id))
                    usage = result.scalar_one_or_none()
                    if usage is None:
                        usage = LLMUsage(user_id=selected_user_id, used=0, limit=new_limit)
                        session.add(usage)
                    else:
                        usage.limit = new_limit
                    await session.commit()
                    
                    # Получаем обновленную информацию о пользователе
                    user_info = await get_user_info(selected_user_id)
                    await update.message.reply_text(f"Лимит для пользователя установлен в {new_limit}.\n\n{user_info}")
            except ValueError:
                await update.message.reply_text("Ошибка: введите корректное число.")
            
            context.user_data["awaiting_limit_for_user"] = False
            return
        
        # Кнопка "Включить LLM" (глобально)
        if text == "Включить LLM":
            async with async_session() as session:
                result = await session.execute(select(LLMConfig))
                config = result.scalars().first()
                if config is None:
                    config = LLMConfig(enabled=True)
                    session.add(config)
                else:
                    config.enabled = True
                await session.commit()
            await update.message.reply_text("LLM функция включена.")
            return
            
        # Кнопка "Выключить LLM" (глобально)
        if text == "Выключить LLM":
            async with async_session() as session:
                result = await session.execute(select(LLMConfig))
                config = result.scalars().first()
                if config is None:
                    config = LLMConfig(enabled=False)
                    session.add(config)
                else:
                    config.enabled = False
                await session.commit()
            await update.message.reply_text("LLM функция отключена.")
            return

    # Удаляем дублирующийся код обработки обратной связи
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


# Новый обработчик для фотографий
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await register_user(update, context)  # Автоматическая регистрация пользователя
    if not await check_rate_limit(user_id):
        await update.message.reply_text("Слишком много запросов. Пожалуйста, подождите.")
        return

    # Получаем фото с наилучшим качеством
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    
    # Получаем подпись к фотографии (если есть)
    caption = update.message.caption
    
    # Сохраняем изображение в Minio
    try:
        image_path = await save_image(photo_bytes, str(user_id))
        
        # Сохраняем информацию о загруженном изображении в БД
        async with async_session() as session:
            user_image = UserImage(user_id=str(user_id), image_path=image_path)
            session.add(user_image)
            await session.commit()
            
            # Логируем загрузку изображения
            log = Log(user_id=str(user_id), message=f"Uploaded image: {image_path}")
            session.add(log)
            await session.commit()
        
        # Проверяем, есть ли подпись к фотографии
        if caption:
            # Если есть подпись, сразу отправляем запрос в LLM
            # Проверка, включена ли LLM-функциональность глобально и для пользователя
            async with async_session() as session:
                config_result = await session.execute(select(LLMConfig))
                config = config_result.scalars().first()
                if config is None or not config.enabled:
                    await update.message.reply_text("LLM функция временно отключена.")
                    return
                
                # Проверка, включена ли LLM-функциональность для конкретного пользователя
                user_result = await session.execute(select(User).where(User.tg_id == str(user_id)))
                user = user_result.scalar_one_or_none()
                if user is None or not user.llm_enabled:
                    await update.message.reply_text("LLM функция отключена для вашего аккаунта.")
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
                
                # Получаем модель LLM для пользователя
                user_model = user.llm_model
            
            # Конвертируем изображение в base64
            try:
                image_base64 = await image_to_base64(image_path)
                
                # Получаем ответ от LLM
                response_text = await get_llm_response(caption, model=user_model, image_base64=image_base64)
                
                # Сохраняем запрос и ответ в БД и увеличиваем счётчик использования
                async with async_session() as session:
                    llm_req = LLMRequest(user_id=str(user_id), prompt=caption, response=response_text)
                    session.add(llm_req)
                    # Обновляем лимит
                    result = await session.execute(select(LLMUsage).where(LLMUsage.user_id == str(user_id)))
                    usage = result.scalar_one_or_none()
                    if usage:
                        usage.used += 1
                    await session.commit()
                
                # Отправляем ответ пользователю
                await update.message.reply_text(
                    response_text,
                    parse_mode="HTML",
                    reply_to_message_id=update.message.message_id,
                )
            except Exception as e:
                async with async_session() as session:
                    log = Log(user_id=str(user_id), message=f"Error processing image with caption for LLM: {str(e)}")
                    session.add(log)
                    await session.commit()
                await update.message.reply_text(
                    f"Произошла ошибка при обработке запроса: {str(e)}",
                    reply_to_message_id=update.message.message_id,
                )
        else:
            # Если нет подписи, сохраняем изображение для следующего запроса
            user_last_image[str(user_id)] = image_path
            
            # Проверяем, включена ли LLM-функциональность для пользователя
            async with async_session() as session:
                user_result = await session.execute(select(User).where(User.tg_id == str(user_id)))
                user = user_result.scalar_one_or_none()
                
                if user and user.llm_enabled:
                    await update.message.reply_text(
                        "Изображение успешно загружено. Теперь вы можете задать вопрос о нём, и я отправлю его вместе с вашим запросом в LLM."
                    )
                else:
                    await update.message.reply_text(
                        "Изображение успешно загружено. Обратите внимание, что функция LLM отключена для вашего аккаунта."
                    )
    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка при загрузке изображения: {str(e)}")
        async with async_session() as session:
            log = Log(user_id=str(user_id), message=f"Error uploading image: {str(e)}")
            session.add(log)
            await session.commit()


# Обновленный обработчик для LLM-запросов
async def llm_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await register_user(update, context)  # Автоматическая регистрация пользователя
    if not await check_rate_limit(user_id):
        await update.message.reply_text("Слишком много запросов. Пожалуйста, подождите.")
        return

    prompt = update.message.text

    # Проверка, включена ли LLM-функциональность глобально
    async with async_session() as session:
        config_result = await session.execute(select(LLMConfig))
        config = config_result.scalars().first()
        if config is None or not config.enabled:
            await update.message.reply_text("LLM функция временно отключена.")
            return
        
        # Проверка, включена ли LLM-функциональность для конкретного пользователя
        user_result = await session.execute(select(User).where(User.tg_id == str(user_id)))
        user = user_result.scalar_one_or_none()
        if user is None or not user.llm_enabled:
            await update.message.reply_text("LLM функция отключена для вашего аккаунта.")
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
        
        # Получаем модель LLM для пользователя
        user_model = user.llm_model
    
    # Проверяем, есть ли у пользователя последнее загруженное изображение
    image_base64 = None
    if str(user_id) in user_last_image:
        try:
            image_path = user_last_image[str(user_id)]
            image_base64 = await image_to_base64(image_path)
            # Удаляем изображение из словаря, чтобы оно не использовалось повторно
            del user_last_image[str(user_id)]
        except Exception as e:
            async with async_session() as session:
                log = Log(user_id=str(user_id), message=f"Error processing image for LLM: {str(e)}")
                session.add(log)
                await session.commit()

    # Получаем ответ от LLM
    try:
        response_text = await get_llm_response(prompt, model=user_model, image_base64=image_base64)
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


# Новые обработчики для управления LLM моделью и включением/выключением LLM для пользователя
async def llm_set_model_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != SUPERUSER_TG_ID:
        await update.message.reply_text(
            "У вас нет прав для выполнения этой команды.",
            reply_to_message_id=update.message.message_id,
        )
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Используйте: /llm_set_model <tg_id или @username> <модель>",
            reply_to_message_id=update.message.message_id,
        )
        return

    target_user = args[0]
    model_name = args[1]

    # Определяем, передан ли tg_id или username
    if target_user.startswith("@"):
        username = target_user[1:]  # Убираем символ @
        async with async_session() as session:
            result = await session.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if user is None:
                await update.message.reply_text(
                    f"Пользователь с username {target_user} не найден.",
                    reply_to_message_id=update.message.message_id,
                )
                return
            target_tg_id = user.tg_id
    else:
        target_tg_id = target_user

    # Обновляем модель LLM для пользователя
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == str(target_tg_id)))
        user = result.scalar_one_or_none()
        if user is None:
            await update.message.reply_text(
                f"Пользователь с ID {target_tg_id} не найден.",
                reply_to_message_id=update.message.message_id,
            )
            return
        user.llm_model = model_name
        await session.commit()

    await update.message.reply_text(
        f"Модель LLM для пользователя {target_tg_id} установлена на {model_name}.",
        reply_to_message_id=update.message.message_id,
    )


async def llm_user_enable_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != SUPERUSER_TG_ID:
        await update.message.reply_text(
            "У вас нет прав для выполнения этой команды.",
            reply_to_message_id=update.message.message_id,
        )
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text(
            "Используйте: /llm_user_enable <tg_id или @username>",
            reply_to_message_id=update.message.message_id,
        )
        return

    target_user = args[0]

    # Определяем, передан ли tg_id или username
    if target_user.startswith("@"):
        username = target_user[1:]  # Убираем символ @
        async with async_session() as session:
            result = await session.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if user is None:
                await update.message.reply_text(
                    f"Пользователь с username {target_user} не найден.",
                    reply_to_message_id=update.message.message_id,
                )
                return
            target_tg_id = user.tg_id
    else:
        target_tg_id = target_user

    # Включаем LLM для пользователя
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == str(target_tg_id)))
        user = result.scalar_one_or_none()
        if user is None:
            await update.message.reply_text(
                f"Пользователь с ID {target_tg_id} не найден.",
                reply_to_message_id=update.message.message_id,
            )
            return
        user.llm_enabled = True
        await session.commit()

    await update.message.reply_text(
        f"LLM функция включена для пользователя {target_tg_id}.",
        reply_to_message_id=update.message.message_id,
    )


async def llm_user_disable_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != SUPERUSER_TG_ID:
        await update.message.reply_text(
            "У вас нет прав для выполнения этой команды.",
            reply_to_message_id=update.message.message_id,
        )
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text(
            "Используйте: /llm_user_disable <tg_id или @username>",
            reply_to_message_id=update.message.message_id,
        )
        return

    target_user = args[0]

    # Определяем, передан ли tg_id или username
    if target_user.startswith("@"):
        username = target_user[1:]  # Убираем символ @
        async with async_session() as session:
            result = await session.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if user is None:
                await update.message.reply_text(
                    f"Пользователь с username {target_user} не найден.",
                    reply_to_message_id=update.message.message_id,
                )
                return
            target_tg_id = user.tg_id
    else:
        target_tg_id = target_user

    # Выключаем LLM для пользователя
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == str(target_tg_id)))
        user = result.scalar_one_or_none()
        if user is None:
            await update.message.reply_text(
                f"Пользователь с ID {target_tg_id} не найден.",
                reply_to_message_id=update.message.message_id,
            )
            return
        user.llm_enabled = False
        await session.commit()

    await update.message.reply_text(
        f"LLM функция отключена для пользователя {target_tg_id}.",
        reply_to_message_id=update.message.message_id,
    )


# Функция для получения информации о пользователе
async def get_user_info(user_id):
    async with async_session() as session:
        # Получаем информацию о пользователе
        user_result = await session.execute(select(User).where(User.tg_id == user_id))
        user = user_result.scalar_one_or_none()
        
        if not user:
            return "Пользователь не найден"
        
        display_name = f"{user.full_name}"
        if user.username:
            display_name += f" (@{user.username})"
            
        llm_status = "включен" if user.llm_enabled else "отключен"
        model_info = f"Модель: {user.llm_model}" if user.llm_model else "Модель не установлена"
        
        # Получаем информацию о лимите
        usage_result = await session.execute(select(LLMUsage).where(LLMUsage.user_id == user_id))
        usage = usage_result.scalar_one_or_none()
        limit_info = ""
        if usage:
            limit_info = f"Использовано {usage.used} из {usage.limit} запросов"
        else:
            limit_info = "Лимит не установлен"
        
        return (
            f"Пользователь: {display_name}\n"
            f"ID: {user.tg_id}\n"
            f"LLM: {llm_status}\n"
            f"{model_info}\n"
            f"{limit_info}"
        )


def register_handlers(app):
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("about", about_handler))
    app.add_handler(CommandHandler("feedback", feedback_command_handler))
    app.add_handler(CommandHandler("llm_enable", llm_enable_handler))
    app.add_handler(CommandHandler("llm_disable", llm_disable_handler))
    app.add_handler(CommandHandler("llm_set_limit", llm_set_limit_handler))
    app.add_handler(CommandHandler("llm_set_model", llm_set_model_handler))
    app.add_handler(CommandHandler("llm_user_enable", llm_user_enable_handler))
    app.add_handler(CommandHandler("llm_user_disable", llm_user_disable_handler))
    app.add_handler(CallbackQueryHandler(category_callback, pattern=r"^category:"))
    app.add_handler(CallbackQueryHandler(back_to_categories_callback, pattern=r"^back_to_categories$"))
    app.add_handler(CallbackQueryHandler(subtopic_callback, pattern=r"^subtopic:"))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT, message_handler))
