import logging
from google import genai
from google.genai import types
from google.genai.errors import APIError
from memory_manager import MemoryManager
from web_search import needs_web_search, search_internet

logger = logging.getLogger(__name__)

# Model havzasi (Failover / Limit bo'lganda avtomatik almashtirish zanjiri)
MODEL_POOL = [
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest",
]

SYSTEM_INSTRUCTION = """Siz Telegram tarmog'ida foydalanuvchilar bilan muloqot qiluvchi aqlli, xushmuomala va yordamsevar sun'iy intellektsiz.

QAT'IY QOIDALAR:
1. Siz FAQAT VA FAQAT O'ZBEK TILIDA (lotin yozuvida) javob berishingiz shart.
2. Agar foydalanuvchi boshqa tilda (masalan: rus, ingliz, turk, qozoq, tojik yoki boshqa har qanday tilda) yozsa, hech qanday holatda ushbu tilda javob bermang yoki tarjima qilmang.
   Bunday holatda FAQATGINA quyidagi jumlani qaytaring:
   "Kechirasiz, men ushbu tilda gaplasha olmayman. Iltimos, murojaatingizni o'zbek tilida yuboring."
3. FORMATLASH QOIDALARI:
   - Javoblaringiz Telegram ilovasida chiroyli, toza va oson o'qiladigan bo'lsin.
   - Ortiqcha yoki takroriy yulduzchalarni (masalan: *** yoki ****) aslo ishlatmang.
   - Muhim so'zlarni ajratish uchun me'yorida **qalin** (bold) matndan foydalaning.
   - Ro'yxatlar tuzishda chiroyli belgilardan (• yoki mos emojilardan) foydalaning.
   - Murakkab jadvallar tuzmang, kerak bo'lsa bandlar yoki ro'yxat ko'rinishida yozing.
4. XOTIRA VA MULTIMODAL TAHLIL:
   - Siz oldingi xabarlar tarixini eslab qolasiz va foydalanuvchining avvalgi gaplariga tayangan holda muloqotni izchil davom ettirasiz.
   - Ovozli xabarlar, rasmlar, hujjatlar va internet ma'lumotlarini tahlil qilib, to'liq o'zbek tilida yordam bering.
"""

AUDIO_INSTRUCTION = """Ushbu audio yozuv O'ZBEK TILIDA gapirilgan.

IKKITA ASOSIY VAZIFANI BAJARING:
1. TRANSKRIPSIYA: Ovozli xabardagi barcha nutqni so'zma-so'z, imlo qoidalariga rioya qilgan holda aniq O'zbek lotin yozuvida matnga o'giring.
2. JAVOB: Agar foydalanuvchi ushbu ovozda biron-bir savol bergan bo'lsa, vazifa aytgan bo'lsa yoki so'rov yuborgan bo'lsa, unga to'liq, muloyim va professional tarzda o'zbek tilida javob qaytaring. Agar ovozda savol bo'lmasa, shunchaki xushmuomala xulosa bering.

Javobingizni qat'iy ravishda quyidagi ikki blokda ajratib taqdim eting:
[TRANSKRIPSIYA]
...bu yerda faqat audio matni...
[JAVOB]
...bu yerda foydalanuvchi savoliga sun'iy intellekt javobi...
"""


class GeminiService:
    def __init__(
        self,
        api_key: str,
        primary_model: str = "gemini-3.5-flash-lite",
    ):
        self.client = genai.Client(api_key=api_key)
        self.primary_model = primary_model

        # Model navbatini sozlaymiz (birlamchi model eng boshida bo'ladi)
        self.models = [self.primary_model]
        for m in MODEL_POOL:
            if m not in self.models:
                self.models.append(m)

        self.last_used_model = self.models[0]
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.7,
        )

    async def _generate_with_failover(self, contents: Any) -> tuple[str, str]:
        """Model limitga yetganda avtomatik ravishda boshqa modelga o'tish mexanizmi (Failover)."""
        last_error = None

        for model_name in self.models:
            try:
                response = await self.client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=self.config,
                )
                if response.text:
                    self.last_used_model = model_name
                    return response.text.strip(), model_name
            except APIError as e:
                logger.warning(
                    f"Model '{model_name}' xatolik berdi ({e.code or e}). Keyingi modelga o'tilmoqda..."
                )
                last_error = e
                continue
            except Exception as e:
                logger.warning(f"Model '{model_name}' kutilmagan xato: {e}")
                last_error = e
                continue

        logger.error(f"Barcha modellar muvaffaqiyatsiz tugadi: {last_error}")
        return (
            "Kechirasiz, sun'iy intellekt tarmog'ida yuklama yuqori bo'lgani sababli hozir javob bera olmadim. Iltimos, birozdan so'ng qayta urinib ko'ring.",
            self.models[0],
        )

    async def generate_response_with_memory(
        self,
        user_id: int,
        user_prompt: str,
        memory: MemoryManager,
    ) -> tuple[str, str]:
        """Xotira va kerak bo'lsa real vaqt internet qidiruvini qo'shgan holda javob oladi."""
        # 1. Internetdan ma'lumot izlash kerakmi?
        final_prompt = user_prompt
        if needs_web_search(user_prompt):
            logger.info(f"Savol bo'yicha internetdan qidiruv amalga oshirilmoqda: '{user_prompt}'")
            search_data = await search_internet(user_prompt)
            if search_data:
                final_prompt = (
                    f"[INTERNETDAN TOPILGAN REAL VAQT MA'LUMOTLARI]:\n"
                    f"{search_data}\n\n"
                    f"[FOYDALANUVCHI SAVOLI]:\n{user_prompt}"
                )

        memory.add_user_message(user_id, final_prompt)
        contents = memory.get_contents_for_gemini(user_id)

        bot_reply, used_model = await self._generate_with_failover(contents)

        if bot_reply and not bot_reply.startswith("Kechirasiz, sun'iy intellekt tarmog'ida"):
            memory.add_model_message(user_id, bot_reply)
        else:
            turns = memory.get_user_turns(user_id)
            if turns and turns[-1].role == "user":
                turns.pop()

        return bot_reply, used_model

    async def analyze_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        user_prompt: str,
        user_id: int,
        memory: MemoryManager,
    ) -> tuple[str, str]:
        """Rasmni tahlil qiladi (Failover qo'llangan holda)."""
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        text_part = types.Part.from_text(text=user_prompt)
        contents = [image_part, text_part]

        bot_reply, used_model = await self._generate_with_failover(contents)

        if bot_reply and not bot_reply.startswith("Kechirasiz"):
            memory.add_user_message(user_id, f"[Rasm]: {user_prompt}")
            memory.add_model_message(user_id, bot_reply)

        return bot_reply, used_model

    async def analyze_pdf(
        self,
        file_path: str,
        mime_type: str,
        user_prompt: str,
        user_id: int,
        memory: MemoryManager,
    ) -> tuple[str, str]:
        """PDF faylni tahlil qiladi."""
        uploaded_file = None
        try:
            uploaded_file = await self.client.aio.files.upload(
                file=file_path,
                config=types.UploadFileConfig(mime_type=mime_type),
            )
            contents = [uploaded_file, user_prompt]
            bot_reply, used_model = await self._generate_with_failover(contents)

            if bot_reply and not bot_reply.startswith("Kechirasiz"):
                memory.add_user_message(user_id, f"[PDF]: {user_prompt}")
                memory.add_model_message(user_id, bot_reply)

            return bot_reply, used_model
        finally:
            if uploaded_file:
                try:
                    await self.client.aio.files.delete(name=uploaded_file.name)
                except Exception as del_err:
                    logger.warning(f"Fayl o'chirishda ogohlantirish: {del_err}")

    async def process_voice_message(
        self,
        file_path: str,
        mime_type: str,
    ) -> tuple[str, str, str]:
        """Ovozli xabarni transkripsiya qiladi va savoliga javob beradi.
        
        Qaytaradi: (transkripsiya_matni, ai_javobi, ishlatilgan_model)
        """
        uploaded_file = None
        try:
            uploaded_file = await self.client.aio.files.upload(
                file=file_path,
                config=types.UploadFileConfig(mime_type=mime_type),
            )
            contents = [uploaded_file, AUDIO_INSTRUCTION]

            raw_reply, used_model = await self._generate_with_failover(contents)

            # Matndan [TRANSKRIPSIYA] va [JAVOB] qismlarini ajratib olamiz
            transcription = ""
            answer = ""

            if "[TRANSKRIPSIYA]" in raw_reply and "[JAVOB]" in raw_reply:
                parts = raw_reply.split("[JAVOB]")
                trans_part = parts[0].replace("[TRANSKRIPSIYA]", "").strip()
                ans_part = parts[1].strip()
                transcription = trans_part
                answer = ans_part
            else:
                # Agar model bloklarga ajratmagan bo'lsa
                transcription = raw_reply
                answer = raw_reply

            return transcription, answer, used_model

        finally:
            if uploaded_file:
                try:
                    await self.client.aio.files.delete(name=uploaded_file.name)
                except Exception as del_err:
                    logger.warning(f"Audio fayl o'chirishda ogohlantirish: {del_err}")
