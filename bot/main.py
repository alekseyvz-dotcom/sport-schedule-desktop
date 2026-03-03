import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import settings
from bot.handlers.user import router as user_router
from bot.handlers.staff import router as staff_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("bot")


async def main():
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(user_router)
    dp.include_router(staff_router)

    await bot.set_my_commands([
        BotCommand(command="book", description="Забронировать площадку"),
        BotCommand(command="my", description="Мои заявки"),
        BotCommand(command="help", description="Помощь"),
    ])

    log.info("Bot starting polling...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        log.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
