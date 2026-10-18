import os
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import config
from bot.database import Database
from bot.sorsa_client import SorsaClient
from bot.handlers import all_routers


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("EngagementBot")


async def main():
    if not config.BOT_TOKEN or config.BOT_TOKEN == "your_telegram_bot_token_here":
        logger.error(
            "BOT_TOKEN is missing or not configured! "
            "Please add your Telegram Bot Token in .env or Render environment variables."
        )
        sys.exit(1)

    # Initialize Database
    db = Database(config.DATABASE_PATH)
    await db.init_db()

    # Sync any initial keys from .env to the database pool
    if config.SORSA_API_KEYS:
        added, dups = await db.add_sorsa_keys(config.SORSA_API_KEYS)
        if added > 0:
            logger.info("Imported %d Sorsa API key(s) into the database pool.", added)

    # Initialize Sorsa API Client with Database pool
    sorsa = SorsaClient(
        api_keys=config.SORSA_API_KEYS,
        base_url=config.SORSA_API_BASE_URL,
        db=db
    )

    key_stats = await db.get_sorsa_keys_stats()
    if key_stats["active"] == 0:
        logger.warning(
            "⚠️ No active Sorsa API keys found in pool! "
            "Please add keys using the /addkeys command in Telegram or set SORSA_API_KEYS in environment."
        )
    else:
        logger.info(
            "🔑 Sorsa Key Pool ready: %d active, %d rate-limited, %d total keys.",
            key_stats["active"], key_stats["rate_limited"], key_stats["total"]
        )

    # Start Render health-check HTTP server if PORT is provided
    web_runner = None
    port_str = os.getenv("PORT")
    if port_str:
        try:
            from aiohttp import web
            port = int(port_str)
            app = web.Application()

            async def handle_ping(request):
                return web.Response(text="OK - Telegram Engagement Bot is active!")

            app.router.add_get("/", handle_ping)
            app.router.add_get("/health", handle_ping)
            web_runner = web.AppRunner(app)
            await web_runner.setup()
            site = web.TCPSite(web_runner, "0.0.0.0", port)
            await site.start()
            logger.info("Render health-check web server listening on port %d", port)
        except Exception as e:
            logger.warning("Could not start HTTP server on PORT %s: %s", port_str, e)

    # Initialize Bot & Dispatcher
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Dependency Injection into handlers
    dp["db"] = db
    dp["sorsa"] = sorsa

    # Register Routers
    for router in all_routers:
        dp.include_router(router)

    logger.info("Starting Telegram Bot with %d assigned posts per submission...", config.ASSIGNMENT_COUNT)

    try:
        # Drop pending updates to avoid processing backlog
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down bot...")
        if web_runner:
            await web_runner.cleanup()
        await sorsa.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
