from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.future import select
from bot.database import async_session
from bot.models import Category, Subtopic


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
