import datetime
import os
import sqlite3
from typing import Any

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_database.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Ma'lumotlar bazasi jadvallarini yaratadi."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Foydalanuvchilar jadvali
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                created_at TIMESTAMP,
                last_seen TIMESTAMP
            )
            """
        )

        # Barcha xabarlar va javoblar logi
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                msg_type TEXT,
                user_text TEXT,
                bot_response TEXT,
                model_used TEXT,
                created_at TIMESTAMP
            )
            """
        )

        # Admin sozlamalari (bildirishnomalar va h.k.)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

        # Standart bildirishnoma sozlamasi: yoqilgan (1)
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('notify_admin', '1')"
        )
        conn.commit()


def add_or_update_user(
    user_id: int,
    first_name: str | None,
    last_name: str | None,
    username: str | None,
):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (user_id, first_name, last_name, username, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                username=excluded.username,
                last_seen=excluded.last_seen
            """,
            (user_id, first_name or "", last_name or "", username or "", now, now),
        )
        conn.commit()


def log_dialogue(
    user_id: int,
    msg_type: str,
    user_text: str,
    bot_response: str,
    model_used: str,
):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO messages_log (user_id, msg_type, user_text, bot_response, model_used, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, msg_type, user_text, bot_response, model_used, now),
        )
        conn.commit()


def get_statistics() -> dict[str, Any]:
    """Admin uchun umumiy statistikani hisoblaydi."""
    today_str = datetime.datetime.now().strftime("%Y-%m-%d") + "%"
    with get_connection() as conn:
        cursor = conn.cursor()

        # Jami foydalanuvchilar
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        # Jami so'rovlar
        cursor.execute("SELECT COUNT(*) FROM messages_log")
        total_queries = cursor.fetchone()[0]

        # Bugungi so'rovlar
        cursor.execute(
            "SELECT COUNT(*) FROM messages_log WHERE created_at LIKE ?",
            (today_str,),
        )
        today_queries = cursor.fetchone()[0]

        # Formatlar bo'yicha taqsimot
        cursor.execute(
            "SELECT msg_type, COUNT(*) as cnt FROM messages_log GROUP BY msg_type"
        )
        type_counts = {row["msg_type"]: row["cnt"] for row in cursor.fetchall()}

        return {
            "total_users": total_users,
            "total_queries": total_queries,
            "today_queries": today_queries,
            "type_counts": type_counts,
        }


def get_recent_dialogues(limit: int = 10, offset: int = 0) -> list[dict]:
    """Oxirgi savol-javoblar tarixini foydalanuvchi ma'lumotlari bilan qaytaradi."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT m.id, m.user_id, m.msg_type, m.user_text, m.bot_response, m.model_used, m.created_at,
                   u.first_name, u.username
            FROM messages_log m
            LEFT JOIN users u ON m.user_id = u.user_id
            ORDER BY m.id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_all_users(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, first_name, username, created_at, last_seen,
                   (SELECT COUNT(*) FROM messages_log WHERE user_id = users.user_id) as msg_count
            FROM users
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


def export_all_logs_text() -> str:
    """Barcha suhbatlar tarixini matnli hisobot (TXT) sifatida shakllantiradi."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT m.id, m.user_id, m.msg_type, m.user_text, m.bot_response, m.model_used, m.created_at,
                   u.first_name, u.username
            FROM messages_log m
            LEFT JOIN users u ON m.user_id = u.user_id
            ORDER BY m.id ASC
            """
        )
        rows = cursor.fetchall()

    lines = [
        "==================================================",
        "TELEGRAM GEMINI AI BOT - BARCHA SUHBATLAR TARIXI",
        f"Eksport vaqti: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Jami yozuvlar: {len(rows)} ta",
        "==================================================\n",
    ]

    for r in rows:
        uname = f"@{r['username']}" if r["username"] else "mavjud emas"
        lines.append(f"[{r['created_at']}] ID: {r['user_id']} | Foydalanuvchi: {r['first_name']} ({uname})")
        lines.append(f"Turi: {r['msg_type']} | Model: {r['model_used']}")
        lines.append(f"SAVOL: {r['user_text']}")
        lines.append(f"JAVOB: {r['bot_response']}")
        lines.append("-" * 50 + "\n")

    return "\n".join(lines)


def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()


# Baza ishga tushirish
init_db()
