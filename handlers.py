import io
import logging
import os
import re
import tempfile
from aiogram import Router, F, Bot
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from database import (
    add_or_update_user,
    log_dialogue,
    get_statistics,
    get_recent_dialogues,
    get_all_users,
    export_all_logs_text,
    get_setting,
    set_setting,
)
from document_parser import (
    extract_text_from_docx,
    extract_text_from_excel,
    extract_text_from_plain_text,
)
from formatter import markdown_to_telegram_html, strip_html_tags
from gemini_service import GeminiService
from keyboards import (
    get_main_keyboard,
    get_clear_confirm_inline_keyboard,
    get_admin_inline_keyboard,
)
from memory_manager import MemoryManager

logger = logging.getLogger(__name__)

router = Router(name="main_router")

MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 Megabayt
MAX_AUDIO_SIZE = 20 * 1024 * 1024  # 20 Megabayt


def split_text(text: str, max_chunk_size: int = 4000) -> list[str]:
    """Telegram xabarlarining 4096 belgililik chegarasiga moslab bo'laklaydi."""
    if len(text) <= max_chunk_size:
        return [text]

    chunks = []
    while len(text) > max_chunk_size:
        split_idx = text.rfind("\n", 0, max_chunk_size)
        if split_idx == -1:
            split_idx = text.rfind(" ", 0, max_chunk_size)
        if split_idx == -1:
            split_idx = max_chunk_size

        chunks.append(text[:split_idx].strip())
        text = text[split_idx:].strip()

    if text:
        chunks.append(text)
    return chunks


async def reply_safe_html(message: Message, formatted_text: str):
    """HTML xabarni xavfsiz jo'natadi, xatolik bo'lsa oddiy matnga o'tadi."""
    chunks = split_text(formatted_text)
    for chunk in chunks:
        try:
            await message.reply(chunk, parse_mode="HTML")
        except TelegramBadRequest as err:
            logger.warning(
                f"HTML parse xatosi ({err}), xavfsiz oddiy matn ko'rinishida yuborilmoqda"
            )
            safe_text = strip_html_tags(chunk)
            await message.reply(safe_text)


async def notify_admin_if_enabled(
    bot: Bot,
    admin_id: int,
    user: Message,
    msg_type: str,
    user_text: str,
    bot_response: str,
):
    """Agar jonli bildirishnoma yoqilgan bo'lsa, adminga yangi muloqot haqida xabar beradi."""
    if not admin_id or user.from_user.id == admin_id:
        return

    is_enabled = get_setting("notify_admin", "1") == "1"
    if not is_enabled:
        return

    u = user.from_user
    u_name = u.first_name or "Foydalanuvchi"
    u_user = f"@{u.username}" if u.username else "yo'q"

    short_q = user_text[:200] + ("..." if len(user_text) > 200 else "")
    short_a = bot_response[:200] + ("..." if len(bot_response) > 200 else "")

    notify_text = (
        f"🔔 <b>Yangi muloqot xabarnomasi:</b>\n"
        f"👤 <b>Foydalanuvchi:</b> {u_name} ({u_user})\n"
        f"🆔 <b>ID:</b> <code>{u.id}</code>\n"
        f"📌 <b>Format:</b> {msg_type}\n\n"
        f"❓ <b>Savol:</b> {short_q}\n\n"
        f"🤖 <b>Javob:</b> {short_a}"
    )

    try:
        await bot.send_message(chat_id=admin_id, text=notify_text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Adminga bildirishnoma jo'natib bo'lmadi: {e}")


def register_handlers(
    gemini_service: GeminiService,
    memory: MemoryManager,
    admin_id: int,
):
    """Routerga barcha hodisa va xabar qayta ishlovchilarini bog'laydi."""

    # 0. Telegram ID ko'rish buyrug'i
    @router.message(Command("myid"))
    async def cmd_myid(message: Message):
        uid = message.from_user.id
        role = "👑 Admin" if uid == admin_id else "Foydalanuvchi"
        await message.reply(
            f"Sizning Telegram ID raqamingiz: <code>{uid}</code>\nRol: <b>{role}</b>",
            parse_mode="HTML",
        )

    # 1. Start buyrug'i
    @router.message(CommandStart())
    async def cmd_start(message: Message):
        user = message.from_user
        is_admin = user.id == admin_id
        add_or_update_user(user.id, user.first_name, user.last_name, user.username)

        admin_badge = " [👑 Administrator]" if is_admin else ""
        welcome_text = (
            f"Assalomu alaykum, <b>{user.first_name}</b>{admin_badge}!\n\n"
            f"🤖 Men Gemini sun'iy intellekti bilan ishlaydigan <b>ko'p funksiyali</b> Telegram botman.\n\n"
            f"🌟 <b>Imkoniyatlar:</b>\n"
            f"• <b>🌐 Real-vaqt Internet qidiruvi:</b> Ob-havo, kurslar, dolzarb yangiliklar.\n"
            f"• <b>🎙 Ovozli muloqot:</b> Ovozda savol bering — bot o'zbek tilida javob beradi va TXT fayl taqdim etadi.\n"
            f"• <b>⚡️ Multi-Model Failover:</b> Uzluksiz va limitsiz avtomatik model almashuvi.\n"
            f"• <b>🖼 Rasm va Hujjatlar:</b> PDF, Word, Excel, matnli fayllar (2 MB gacha).\n"
            f"• <b>🧠 Xotira:</b> 20–50 ta so'nggi xabarni eslab qoladi.\n"
        )
        if is_admin:
            welcome_text += "\n👑 <b>Siz adminsiz!</b> Pastdagi <b>'👑 Admin panel'</b> tugmasi orqali barcha savol-javoblarni kuzatishingiz mumkin."

        await message.answer(
            welcome_text,
            parse_mode="HTML",
            reply_markup=get_main_keyboard(is_admin),
        )

    # 2. Yordam buyrug'i
    @router.message(Command("help"))
    @router.message(F.text.func(lambda t: t and "yordam" in t.lower()))
    async def cmd_help(message: Message):
        is_admin = message.from_user.id == admin_id
        help_text = (
            "ℹ️ <b>Botdan foydalanish bo'yicha qo'llanma:</b>\n\n"
            "1. <b>Matn:</b> Istalgan mavzuda savol bering. Kerak bo'lsa bot avtomatik tarzda internetdan ma'lumot qidirib javob beradi.\n"
            "2. <b>Ovozli xabar:</b> Ovoz jo'natsangiz, bot savolingizga javob qaytaradi va matnini TXT fayl qilib beradi.\n"
            "3. <b>Rasm va Fayllar:</b> Rasm yoki PDF, Word, Excel (2 MB gacha) fayllarni jo'nating.\n"
            "4. <b>Xotira:</b> Pastdagi tugmalar orqali xotira holatini tekshirish yoki tozalash mumkin."
        )
        await message.answer(
            help_text,
            parse_mode="HTML",
            reply_markup=get_main_keyboard(is_admin),
        )

    # 3. ADMIN PANEL VA BOSHQARUV (Har qanday "admin" so'zi orqali ham ochiladi)
    @router.message(Command("admin"))
    @router.message(F.text.func(lambda t: t and "admin" in t.lower()))
    async def cmd_admin(message: Message):
        user_id = message.from_user.id
        if user_id != admin_id:
            await message.reply("⛔️ Bu bo'lim faqat bot administratori uchun mo'ljallangan.")
            return

        stats = get_statistics()
        notify_status = get_setting("notify_admin", "1") == "1"

        admin_text = (
            "👑 <b>Boshqaruv Admin Paneli</b>\n\n"
            f"👥 <b>Jami foydalanuvchilar:</b> {stats['total_users']} ta\n"
            f"💬 <b>Jami so'rovlar:</b> {stats['total_queries']} ta\n"
            f"📅 <b>Bugungi so'rovlar:</b> {stats['today_queries']} ta\n"
            f"🔄 <b>Faol model:</b> <code>{gemini_service.last_used_model}</code>\n\n"
            "Quyidagi tugmalar orqali barcha muloqotlar va foydalanuvchilarni kuzatishingiz mumkin:"
        )
        await message.answer(
            admin_text,
            parse_mode="HTML",
            reply_markup=get_admin_inline_keyboard(notify_status),
        )

    # Admin Callback: To'liq statistika
    @router.callback_query(F.data == "admin_stats")
    async def cb_admin_stats(callback: CallbackQuery):
        if callback.from_user.id != admin_id:
            await callback.answer("Ruxsat yo'q!", show_alert=True)
            return

        stats = get_statistics()
        types_info = "\n".join(
            [f"• {k.capitalize()}: {v} ta" for k, v in stats["type_counts"].items()]
        ) or "Ma'lumot yo'q"

        text = (
            "📊 <b>Batafsil statistika:</b>\n\n"
            f"👥 Foydalanuvchilar soni: <b>{stats['total_users']}</b>\n"
            f"💬 Jami muloqotlar: <b>{stats['total_queries']}</b>\n"
            f"📅 Bugun: <b>{stats['today_queries']}</b>\n\n"
            f"<b>Formatlar bo'yicha:</b>\n{types_info}\n\n"
            f"<b>Model zanjiri (Failover):</b>\n"
            + "\n".join([f"• <code>{m}</code>" for m in gemini_service.models])
        )
        notify_status = get_setting("notify_admin", "1") == "1"
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_admin_inline_keyboard(notify_status),
        )

    # Admin Callback: So'nggi muloqotlar
    @router.callback_query(F.data == "admin_recent_logs")
    async def cb_admin_recent_logs(callback: CallbackQuery):
        if callback.from_user.id != admin_id:
            await callback.answer("Ruxsat yo'q!", show_alert=True)
            return

        dialogues = get_recent_dialogues(limit=7)
        if not dialogues:
            await callback.answer("Hali muloqotlar mavjud emas.", show_alert=True)
            return

        lines = ["📜 <b>So'nggi savol-javoblar:</b>\n"]
        for d in dialogues:
            u_name = d["first_name"] or "Foydalanuvchi"
            uname = f"@{d['username']}" if d["username"] else f"ID:{d['user_id']}"
            q = (d["user_text"] or "")[:120].replace("<", "&lt;").replace(">", "&gt;")
            a = (d["bot_response"] or "")[:150].replace("<", "&lt;").replace(">", "&gt;")
            lines.append(
                f"👤 <b>{u_name}</b> ({uname}) [{d['created_at'][11:16]}]:\n"
                f"❓ <i>{q}</i>\n"
                f"🤖 <b>AI ({d['model_used']}):</b> {a}\n"
                f"{'-'*30}"
            )

        text = "\n".join(lines)
        notify_status = get_setting("notify_admin", "1") == "1"
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_admin_inline_keyboard(notify_status),
        )

    # Admin Callback: Foydalanuvchilar
    @router.callback_query(F.data == "admin_users")
    async def cb_admin_users(callback: CallbackQuery):
        if callback.from_user.id != admin_id:
            await callback.answer("Ruxsat yo'q!", show_alert=True)
            return

        users = get_all_users(limit=15)
        lines = ["👥 <b>Foydalanuvchilar ro'yxati (so'nggi faollar):</b>\n"]
        for u in users:
            uname = f"@{u['username']}" if u["username"] else "yo'q"
            lines.append(
                f"• <b>{u['first_name']}</b> ({uname}) | ID: <code>{u['user_id']}</code>\n"
                f"  So'rovlar: {u['msg_count']} ta | Oxirgi: {u['last_seen']}"
            )

        text = "\n".join(lines)
        notify_status = get_setting("notify_admin", "1") == "1"
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_admin_inline_keyboard(notify_status),
        )

    # Admin Callback: Barcha tarixni TXT formatda yuklab olish
    @router.callback_query(F.data == "admin_export_txt")
    async def cb_admin_export(callback: CallbackQuery):
        if callback.from_user.id != admin_id:
            await callback.answer("Ruxsat yo'q!", show_alert=True)
            return

        await callback.answer("Fayl tayyorlanmoqda...", show_alert=False)
        report_text = export_all_logs_text()
        doc_file = BufferedInputFile(
            report_text.encode("utf-8"),
            filename="barcha_muloqotlar_tarixi.txt",
        )
        await callback.message.reply_document(
            document=doc_file,
            caption="📥 <b>Barcha foydalanuvchilar muloqotlari tarixi (To'liq hisobot).</b>",
            parse_mode="HTML",
        )

    # Admin Callback: Jonli xabardorlikni o'zgartirish (Toggle)
    @router.callback_query(F.data == "admin_toggle_notify")
    async def cb_admin_toggle_notify(callback: CallbackQuery):
        if callback.from_user.id != admin_id:
            await callback.answer("Ruxsat yo'q!", show_alert=True)
            return

        current = get_setting("notify_admin", "1") == "1"
        new_val = "0" if current else "1"
        set_setting("notify_admin", new_val)

        state_word = "O'chirildi 🔴" if current else "Yoqildi 🟢"
        await callback.answer(f"Jonli xabardorlik {state_word}", show_alert=False)

        notify_status = new_val == "1"
        await callback.message.edit_reply_markup(
            reply_markup=get_admin_inline_keyboard(notify_status)
        )

    # 4. XOTIRA BOSHQARUVI
    @router.message(Command("memory"))
    @router.message(F.text.func(lambda t: t and "xotira holati" in t.lower()))
    async def show_memory_status(message: Message):
        user_id = message.from_user.id
        status = memory.get_memory_status(user_id)
        is_admin = user_id == admin_id

        if status["is_full"]:
            status_note = "⚠️ Xotira to'lgan (50 ta xabar). Yangi xabar kelganda eng eski xabarlar yangilanib boradi."
        elif status["total"] == 0:
            status_note = "🟢 Xotira bo'sh. Hozircha hech qanday xabar saqlanmagan."
        elif status["total"] < status["min_limit"]:
            status_note = f"🟢 Xotira faol (hali {status['min_limit']} ta chegaraga yetmadi)."
        else:
            status_note = "🟡 Xotira to'lib bormoqda (20 dan 50 tagacha bo'lgan oraliqda)."

        text = (
            "🧠 <b>Xotira boshqaruv paneli:</b>\n\n"
            f"• <b>Saqlangan xabarlar:</b> <b>{status['total']}</b> / {status['max_limit']} ta\n"
            f"• <b>To'lganlik holati:</b> <code>{status['progress_bar']}</code>\n"
            f"• <b>Sizning savollaringiz:</b> {status['user_msgs']} ta\n"
            f"• <b>Bot javoblari:</b> {status['model_msgs']} ta\n"
            f"• <b>Xotira sig'imi:</b> min {status['min_limit']} ta — max {status['max_limit']} ta\n\n"
            f"💡 <i>{status_note}</i>"
        )
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_main_keyboard(is_admin),
        )

    @router.message(Command("clear"))
    @router.message(F.text.func(lambda t: t and "xotirani tozalash" in t.lower()))
    async def request_clear_memory(message: Message):
        user_id = message.from_user.id
        status = memory.get_memory_status(user_id)
        is_admin = user_id == admin_id

        if status["total"] == 0:
            await message.answer(
                "ℹ️ Xotira allaqachon bo'sh, tozalashga hojat yo'q.",
                reply_markup=get_main_keyboard(is_admin),
            )
            return

        text = (
            f"⚠️ <b>Haqiqatan ham suhbat xotirasini tozalamoqchimisiz?</b>\n\n"
            f"Hozirda xotirada <b>{status['total']} ta xabar</b> saqlangan. "
            f"Tozalangandan so'ng bot avvalgi suhbatlarni eslay olmaydi."
        )
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_clear_confirm_inline_keyboard(),
        )

    @router.callback_query(F.data == "confirm_clear_memory")
    async def confirm_clear(callback: CallbackQuery):
        user_id = callback.from_user.id
        memory.clear_memory(user_id)
        await callback.answer("Xotira tozalandi!", show_alert=False)
        await callback.message.edit_text(
            "✅ <b>Suhbat xotirasi muvaffaqiyatli tozalandi!</b>\n\n"
            "Endi bot bilan yangi mavzuda suhbatni noldan boshlashingiz mumkin.",
            parse_mode="HTML",
        )

    @router.callback_query(F.data == "cancel_clear_memory")
    async def cancel_clear(callback: CallbackQuery):
        await callback.answer("Tozalash bekor qilindi.", show_alert=False)
        await callback.message.edit_text(
            "❌ <b>Xotirani tozalash bekor qilindi.</b>\n"
            "Muloqot tarixi o'zgarishsiz qoldirildi.",
            parse_mode="HTML",
        )

    # 5. OVOZLI XABARLAR VA AUDIO (O'zbekcha transkripsiya + Savolga javob)
    @router.message(F.voice | F.audio)
    async def handle_audio(message: Message, bot: Bot):
        user = message.from_user
        add_or_update_user(user.id, user.first_name, user.last_name, user.username)

        audio_obj = message.voice if message.voice else message.audio
        file_size = audio_obj.file_size or 0

        if file_size > MAX_AUDIO_SIZE:
            size_mb = file_size / (1024 * 1024)
            await message.reply(
                f"⚠️ <b>Audio hajmi juda katta!</b>\n\n"
                f"Ovozli xabar yoki audio fayl hajmi ko'pi bilan <b>20 MB</b> bo'lishi kerak.\n"
                f"Siz yuborgan fayl: <b>{size_mb:.2f} MB</b>.",
                parse_mode="HTML",
            )
            return

        status_msg = await message.reply(
            "🎙 <b>Ovozli xabar qabul qilindi.</b>\n"
            "Matnga o'girilmoqda va javob tayyorlanmoqda, iltimos kuting...",
            parse_mode="HTML",
        )

        is_voice = bool(message.voice)
        suffix = ".ogg" if is_voice else ".mp3"
        mime_type = "audio/ogg" if is_voice else (audio_obj.mime_type or "audio/mpeg")

        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        temp_path = temp_file.name
        temp_file.close()

        try:
            await bot.download(audio_obj, destination=temp_path)

            transcription, answer, model_used = await gemini_service.process_voice_message(
                file_path=temp_path,
                mime_type=mime_type,
            )

            # TXT fayl tayyorlash
            full_txt_content = (
                f"--- OVOZLI XABAR TRANSKRIPSIYASI ---\n\n"
                f"{transcription}\n\n"
                f"--- SUN'IY INTELLEKT JAVOBI ---\n\n"
                f"{answer}\n"
            )
            txt_file = BufferedInputFile(
                full_txt_content.encode("utf-8"),
                filename="ovoz_transkripsiya.txt",
            )

            # Javobni xotiraga qo'shish
            memory.add_user_message(user.id, f"[Ovozli xabar]: {transcription}")
            memory.add_model_message(user.id, answer)

            # Bazaga yozish
            log_dialogue(user.id, "voice", transcription, answer, model_used)

            # Adminga bildirishnoma
            await notify_admin_if_enabled(
                bot, admin_id, message, "voice", transcription, answer
            )

            # Chatga AI javobini yuborish
            formatted_answer = markdown_to_telegram_html(answer)
            await status_msg.delete()

            # Matnli javobni xavfsiz yuboramiz
            await reply_safe_html(message, formatted_answer)

            # TXT transkripsiya faylini taqdim etamiz
            preview = transcription[:150] + ("..." if len(transcription) > 150 else "")
            caption = (
                f"🎙 <b>Ovoz matni (Transkripsiya):</b>\n"
                f"<i>\"{preview}\"</i>\n\n"
                f"To'liq transkripsiya yuqoridagi <b>TXT</b> faylida keltirildi."
            )
            await message.reply_document(
                document=txt_file,
                caption=caption,
                parse_mode="HTML",
            )

        except Exception as e:
            logger.error(f"Audio qayta ishlash xatosi: {e}")
            await status_msg.edit_text(
                "❌ Audio yozuvni qayta ishlashda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",
                parse_mode="HTML",
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # 6. RASMLARNI QAYTA ISHLASH (Photos)
    @router.message(F.photo)
    async def handle_photo(message: Message, bot: Bot):
        user = message.from_user
        add_or_update_user(user.id, user.first_name, user.last_name, user.username)

        user_prompt = (
            message.caption.strip()
            if message.caption
            else "Ushbu rasmni batafsil tahlil qiling va unda nimalar aks etganini chiroyli o'zbek tilida tushuntirib bering."
        )

        await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

        photo = message.photo[-1]
        buffer = io.BytesIO()
        await bot.download(photo, destination=buffer)
        image_bytes = buffer.getvalue()

        raw_response, model_used = await gemini_service.analyze_image(
            image_bytes=image_bytes,
            mime_type="image/jpeg",
            user_prompt=user_prompt,
            user_id=user.id,
            memory=memory,
        )

        log_dialogue(user.id, "photo", user_prompt, raw_response, model_used)
        await notify_admin_if_enabled(
            bot, admin_id, message, "photo", user_prompt, raw_response
        )

        formatted = markdown_to_telegram_html(raw_response)
        await reply_safe_html(message, formatted)

    # 7. HUJJATLAR (PDF, DOCX, EXCEL, TXT — 2 MB gacha)
    @router.message(F.document)
    async def handle_document(message: Message, bot: Bot):
        user = message.from_user
        add_or_update_user(user.id, user.first_name, user.last_name, user.username)

        doc = message.document
        file_size = doc.file_size or 0
        file_name = doc.file_name or "hujjat"
        ext = os.path.splitext(file_name)[1].lower()

        if file_size > MAX_FILE_SIZE:
            size_mb = file_size / (1024 * 1024)
            await message.reply(
                f"⚠️ <b>Fayl hajmi juda katta!</b>\n\n"
                f"Fayl hajmi ko'pi bilan <b>2 MB</b> bo'lishi kerak.\n"
                f"Siz yuborgan fayl: <b>{size_mb:.2f} MB</b>.\n"
                f"Iltimos, 2 MB dan kichikroq hajmdagi fayl yuboring.",
                parse_mode="HTML",
            )
            return

        user_prompt = (
            message.caption.strip()
            if message.caption
            else f"Ushbu '{file_name}' hujjatini to'liq tahlil qiling va undagi asosiy ma'lumotlarni o'zbek tilida tushuntirib bering."
        )

        status_msg = await message.reply(
            f"📄 <b>{file_name}</b> qabul qilindi. Tahlil qilinmoqda...",
            parse_mode="HTML",
        )

        temp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        temp_path = temp_file.name
        temp_file.close()

        try:
            await bot.download(doc, destination=temp_path)

            if ext == ".pdf":
                raw_response, model_used = await gemini_service.analyze_pdf(
                    file_path=temp_path,
                    mime_type="application/pdf",
                    user_prompt=user_prompt,
                    user_id=user.id,
                    memory=memory,
                )
            elif ext in [".docx", ".doc"]:
                extracted = extract_text_from_docx(temp_path)
                full_prompt = (
                    f"Foydalanuvchi Word hujjati ({file_name}) yubordi:\n"
                    f"{extracted[:25000]}\n\n"
                    f"Topshiriq: {user_prompt}"
                )
                raw_response, model_used = await gemini_service.generate_response_with_memory(
                    user_id=user.id,
                    user_prompt=full_prompt,
                    memory=memory,
                )
            elif ext in [".xlsx", ".xls"]:
                extracted = extract_text_from_excel(temp_path)
                full_prompt = (
                    f"Foydalanuvchi Excel hujjati ({file_name}) yubordi:\n"
                    f"{extracted[:25000]}\n\n"
                    f"Topshiriq: {user_prompt}"
                )
                raw_response, model_used = await gemini_service.generate_response_with_memory(
                    user_id=user.id,
                    user_prompt=full_prompt,
                    memory=memory,
                )
            elif ext in [".txt", ".csv", ".json", ".md", ".py", ".html"]:
                extracted = extract_text_from_plain_text(temp_path)
                full_prompt = (
                    f"Foydalanuvchi fayl ({file_name}) yubordi:\n"
                    f"{extracted[:25000]}\n\n"
                    f"Topshiriq: {user_prompt}"
                )
                raw_response, model_used = await gemini_service.generate_response_with_memory(
                    user_id=user.id,
                    user_prompt=full_prompt,
                    memory=memory,
                )
            else:
                await status_msg.edit_text(
                    f"⚠️ Kechirasiz, <b>{ext}</b> formati qo'llab-quvvatlanmaydi.\n"
                    f"Bot <b>PDF, DOCX, XLSX, TXT, CSV, rasm va audio</b> fayllarni tushunadi.",
                    parse_mode="HTML",
                )
                return

            log_dialogue(user.id, "document", f"{file_name}: {user_prompt}", raw_response, model_used)
            await notify_admin_if_enabled(
                bot, admin_id, message, "document", f"{file_name}: {user_prompt}", raw_response
            )

            formatted = markdown_to_telegram_html(raw_response)
            await status_msg.delete()
            await reply_safe_html(message, formatted)

        except Exception as e:
            logger.error(f"Hujjat tahlilida xatolik: {e}")
            await status_msg.edit_text(
                "❌ Kechirasiz, ushbu faylni tahlil qilishda xatolik yuz berdi.",
                parse_mode="HTML",
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # 8. ODDIY MATNLI XABARLAR (Gemini + Internet qidiruvi + Failover + Xotira)
    @router.message(F.text)
    async def handle_text(message: Message, bot: Bot):
        user = message.from_user
        add_or_update_user(user.id, user.first_name, user.last_name, user.username)

        user_text = message.text.strip()
        if not user_text:
            return

        await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

        raw_response, model_used = await gemini_service.generate_response_with_memory(
            user_id=user.id,
            user_prompt=user_text,
            memory=memory,
        )

        log_dialogue(user.id, "text", user_text, raw_response, model_used)
        await notify_admin_if_enabled(
            bot, admin_id, message, "text", user_text, raw_response
        )

        formatted_response = markdown_to_telegram_html(raw_response)
        await reply_safe_html(message, formatted_response)

    return router
