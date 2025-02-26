from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.future import select
from bot.database import async_session
from bot.models import Category, Subtopic, User, LLMModel


async def get_categories_inline_keyboard():
    async with async_session() as session:
        result = await session.execute(select(Category).order_by(Category.display_order))
        categories = result.scalars().all()
        keyboard = []
        for cat in categories:
            keyboard.append([InlineKeyboardButton(cat.name, callback_data=f"category:{cat.id}")])
        return InlineKeyboardMarkup(keyboard)


async def get_subtopics_inline_keyboard(category_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Subtopic).where(Subtopic.category_id == category_id).order_by(Subtopic.display_order)
        )
        subtopics = result.scalars().all()
        keyboard = []
        for sub in subtopics:
            keyboard.append([InlineKeyboardButton(sub.name, callback_data=f"subtopic:{sub.id}")])
        # Добавляем кнопку "Назад" для возврата к категориям
        keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_categories")])
        return InlineKeyboardMarkup(keyboard)


def get_main_reply_keyboard():
    # Постоянная клавиатура с тремя кнопками
    keyboard = [["Основное меню"], ["О боте", "Оставить обратную связь"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_admin_reply_keyboard():
    # Клавиатура для администратора с дополнительной кнопкой "Управление ботом"
    keyboard = [["Основное меню"], ["О боте", "Оставить обратную связь"], ["Управление ботом"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_admin_control_keyboard():
    # Клавиатура для управления ботом (только для суперпользователя)
    keyboard = [
        ["Включить LLM", "Выключить LLM"],
        ["Управление пользователями"],
        ["Назад"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def get_users_keyboard(page=0, page_size=10):
    # Клавиатура для выбора пользователей с пагинацией
    async with async_session() as session:
        # Получаем общее количество пользователей
        total_users_result = await session.execute(select(User))
        total_users = len(total_users_result.scalars().all())
        
        # Получаем пользователей для текущей страницы
        users_result = await session.execute(
            select(User).order_by(User.tg_id).offset(page * page_size).limit(page_size)
        )
        users = users_result.scalars().all()
        
        keyboard = []
        for user in users:
            # Отображаем имя пользователя и его username (если есть)
            display_name = f"{user.full_name}"
            if user.username:
                display_name += f" (@{user.username})"
            keyboard.append([display_name])
        
        # Добавляем кнопки навигации
        navigation = []
        if page > 0:
            navigation.append("◀️ Назад")
        if (page + 1) * page_size < total_users:
            navigation.append("Вперед ▶️")
        if navigation:
            keyboard.append(navigation)
        
        # Добавляем кнопку возврата в меню управления
        keyboard.append(["Вернуться в меню управления"])
        
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_user_actions_keyboard():
    # Клавиатура действий с выбранным пользователем
    keyboard = [
        ["Включить LLM", "Выключить LLM"],
        ["Установить модель", "Установить лимит"],
        ["Назад к списку пользователей"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def get_llm_models_keyboard():
    # Клавиатура для выбора модели LLM
    async with async_session() as session:
        result = await session.execute(select(LLMModel).order_by(LLMModel.name))
        models = result.scalars().all()
        
        keyboard = []
        for model in models:
            # Отображаем название модели и её описание
            keyboard.append([f"{model.name} - {model.description}"])
        
        # Добавляем кнопку для ручного ввода новой модели
        keyboard.append(["Добавить новую модель"])
        
        # Добавляем кнопку возврата
        keyboard.append(["Назад"])
        
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
