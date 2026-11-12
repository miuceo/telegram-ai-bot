import asyncio
import logging
import os
import sys
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from config import load_config
from database import init_db
from gemini_service import GeminiService
from handlers import register_handlers
from keyboards import get_main_keyboard
from memory_manager import MemoryManager

# Loglarni sozlash
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def handle_ping(request):
    """Render va Cron Job (ping) uchun 200 OK qaytaruvchi endpoint."""
    return web.Response(
        text="Telegram AI Bot faol ishlab turibdi! 24/7 Status: 200 OK",
        content_type="text/plain",
    )


async def start_web_server():
    """Render Web Service talab qiladigan HTTP serverni ishga tushiradi."""
    port = int(os.getenv("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Render HTTP server ishga tushdi: http://0.0.0.0:{port}")
    return runner


async def set_main_menu(bot: Bot):
    """Bot menyusiga buyruqlarni o'rnatish."""
    commands = [
        BotCommand(command="start", description="Botni ishga tushirish"),
        BotCommand(command="memory", description="Xotira holati (20-50 xabar)"),
        BotCommand(command="clear", description="Suhbat xotirasini tozalash"),
        BotCommand(command="admin", description="Admin paneli (faqat admin uchun)"),
        BotCommand(command="myid", description="Telegram ID raqamim"),
        BotCommand(command="help", description="Yordam va qo'llanma"),
    ]
    await bot.set_my_commands(commands)


async def main():
    logger.info("Bot (24/7 Render serveriga moslangan) ishga tushirilmoqda...")

    # Baza jadvallarini tekshirish
    init_db()

    # Konfiguratsiyani yuklash
    try:
        config = load_config()
    except ValueError as err:
        logger.error(f"Konfiguratsiya xatosi: {err}")
        print(f"\n[XATOLIK] {err}\n")
        sys.exit(1)

    # Render uchun HTTP serverni ishga tushiramiz
    web_runner = await start_web_server()

    # Gemini xizmatini yaratish (Multi-model failover qo'llab-quvvatlanadi)
    gemini_service = GeminiService(
        api_key=config.gemini_api_key,
        primary_model=config.gemini_model,
    )
    logger.info(f"Gemini modeli ulandi: {config.gemini_model} (Zaxira modellar: {gemini_service.models})")
    logger.info(f"Admin Telegram ID o'rnatildi: {config.admin_id}")

    # Xotira boshqaruvchisi (min 20, max 50 ta xabar)
    memory_manager = MemoryManager(min_limit=20, max_limit=50)

    # Aiogram Bot va Dispatcher yaratish
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()

    # Router va handlerlarni ro'yxatdan o'tkazish
    router = register_handlers(gemini_service, memory_manager, config.admin_id)
    dp.include_router(router)

    # Bot buyruqlarini Telegramga yuborish
    await set_main_menu(bot)

    # Eski kutilayotgan yangilanishlarni tozalash (drop pending updates)
    await bot.delete_webhook(drop_pending_updates=True)

    # Adminga start xabarini yuborish
    if config.admin_id:
        try:
            await bot.send_message(
                chat_id=config.admin_id,
                text=(
                    "🚀 <b>Bot muvaffaqiyatli ishga tushirildi!</b>\n\n"
                    "👑 <b>Admin panel</b> pastdagi menyuda faollashtirildi."
                ),
                parse_mode="HTML",
                reply_markup=get_main_keyboard(is_admin=True),
            )
            logger.info("Adminga xush kelibsiz xabari yuborildi.")
        except Exception as admin_err:
            logger.warning(f"Adminga start xabarini yuborib bo'lmadi: {admin_err}")

    logger.info("Bot muvaffaqiyatli ishga tushdi va xabarlarni kutmoqda...")
    try:
        await dp.start_polling(bot)
    finally:
        await web_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
