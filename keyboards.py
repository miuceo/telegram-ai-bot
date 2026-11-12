from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


def get_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Asosiy pastki boshqaruv paneli."""
    keyboard = [
        [
            KeyboardButton(text="📊 Xotira holati"),
            KeyboardButton(text="🗑 Xotirani tozalash"),
        ],
        [
            KeyboardButton(text="ℹ️ Yordam va qoidalar"),
        ],
    ]

    # Agar admin bo'lsa, maxsus Admin tugmasini qo'shamiz
    if is_admin:
        keyboard.append([KeyboardButton(text="👑 Admin panel")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )


def get_clear_confirm_inline_keyboard() -> InlineKeyboardMarkup:
    """Xotirani tozalashni tasdiqlash uchun inline tugmalar."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ha, tozalansin",
                    callback_data="confirm_clear_memory",
                ),
                InlineKeyboardButton(
                    text="❌ Bekor qilish",
                    callback_data="cancel_clear_memory",
                ),
            ]
        ]
    )


def get_admin_inline_keyboard(notify_enabled: bool) -> InlineKeyboardMarkup:
    """Admin panelidagi boshqaruv tugmalari."""
    bell_status = "Yoqilgan 🟢" if notify_enabled else "O'chirilgan 🔴"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 To'liq statistika",
                    callback_data="admin_stats",
                ),
                InlineKeyboardButton(
                    text="📜 So'nggi 10 muloqot",
                    callback_data="admin_recent_logs",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="👥 Foydalanuvchilar",
                    callback_data="admin_users",
                ),
                InlineKeyboardButton(
                    text="📥 Tarixni olish (TXT)",
                    callback_data="admin_export_txt",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"🔔 Jonli xabardorlik: {bell_status}",
                    callback_data="admin_toggle_notify",
                ),
            ],
        ]
    )
