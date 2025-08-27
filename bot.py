#!/usr/bin/env python3
"""
Telegram AI Assistant - Bot Runner
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from app.config import settings
from app.bot.handlers import router
from app.database.connection import init_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Main function"""
    # Initialize database
    await init_db()
    
    # Initialize bot and dispatcher
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    
    # Register handlers
    dp.include_router(router)
    
    # Setup webhook
    if settings.is_production:
        # Production: use webhook
        app = web.Application()
        
        # Setup webhook handler
        webhook_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot
        )
        webhook_handler.register(app, path="/webhook")
        
        # Start webhook
        await bot.set_webhook(
            url=f"{settings.app_base_url}/webhook",
            secret_token=settings.webhook_secret
        )
        
        # Start web server
        web.run_app(
            app,
            host="0.0.0.0",
            port=8001
        )
    else:
        # Development: use polling
        logger.info("Starting bot in polling mode...")
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
