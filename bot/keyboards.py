from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.future import select
from bot.database import async_session
from bot.models import Category, Subtopic


async def get_main_menu_keyboard():
    async with async_session() as session:
        result = await session.execute(select(Category))
        categories = result.scalars().all()
        # Каждая кнопка располагается в отдельном ряду
        keyboard = [[cat.name] for cat in categories]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    return reply_markup


async def get_subtopics_keyboard(category_name: str):
    async with async_session() as session:
        result = await session.execute(select(Category).where(Category.name == category_name))
        category = result.scalar_one_or_none()
        keyboard = []
        if category:
            result = await session.execute(select(Subtopic).where(Subtopic.category_id == category.id))
            subtopics = result.scalars().all()
            for sub in subtopics:
                keyboard.append([InlineKeyboardButton(sub.name, callback_data=f"subtopic:{sub.id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
    return reply_markup
