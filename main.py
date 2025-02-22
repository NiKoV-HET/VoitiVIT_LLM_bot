from telegram.ext import ApplicationBuilder
from telegram import BotCommand
from bot.config import BOT_TOKEN
from bot.handlers import register_handlers
from bot.database import engine
from bot.models import Base


async def on_startup(app):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    commands = [
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("about", "О боте"),
        BotCommand("feedback", "Оставить обратную связь"),
    ]
    await app.bot.set_my_commands(commands)
    print("Бот запущен.")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()
    register_handlers(app)
    app.run_polling()


if __name__ == "__main__":
    main()
