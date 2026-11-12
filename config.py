import os
from dataclasses import dataclass
from dotenv import load_dotenv

# .env faylini yuklaymiz (mavjud tizim o'zgaruvchilarini saqlab qolgan holda)
load_dotenv(override=False)


@dataclass
class Config:
    bot_token: str
    gemini_api_key: str
    gemini_model: str
    admin_id: int


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    admin_id_raw = os.getenv("ADMIN_ID", "7197666892").strip()

    try:
        admin_id = int(admin_id_raw) if admin_id_raw else 0
    except ValueError:
        admin_id = 0

    if not bot_token:
        raise ValueError(
            "BOT_TOKEN topilmadi! Iltimos, .env faylida BOT_TOKEN ni ko'rsating (Telegram @BotFather dan olinadi)."
        )

    if not gemini_api_key:
        raise ValueError(
            "GEMINI_API_KEY topilmadi! Iltimos, .env faylida yoki tizim muhitida GEMINI_API_KEY ni ko'rsating."
        )

    return Config(
        bot_token=bot_token,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        admin_id=admin_id,
    )
