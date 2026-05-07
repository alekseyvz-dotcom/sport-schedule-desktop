import asyncio
import logging
import socket

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
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
    session = AiohttpSession(timeout=60)

    # Принудительно используем IPv4, чтобы Docker не пытался ходить в Telegram через IPv6
    session._connector_init["family"] = socket.AF_INET

    bot = Bot(
        token=settings.BOT_TOKEN,
        session=session,
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
        await dp.start_polling(
            bot,
            polling_timeout=30,
        )
    finally:
        await bot.session.close()
        log.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
