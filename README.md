# Telegram Gemini AI Bot (24/7 Render & Cron Job Qo'llanmasi)

Ushbu loyiha Google Gemini sun'iy intellekti bilan ishlaydigan ko'p funksiyali Telegram bot bo'lib, Render serverida 24/7 rejimida bepul ishlashga to'liq moslangan.

---

## 🌟 Asosiy imkoniyatlar
- **💬 Matnli muloqot va Xotira (Memory):** 20–50 tagacha so'nggi xabarlar konteksti.
- **🎙 Ovozli muloqot:** Ovozli xabarlarni o'zbek tilida so'zma-so'z transkripsiya qilish va savollarga javob berish (TXT fayl bilan).
- **🌐 Real-vaqt Internet qidiruvi:** Ob-havo, kurslar, dolzarb yangiliklar.
- **⚡️ Multi-Model Failover:** Zaxira modellar zanjiri bilan limitlardan himoyalangan uzluksiz ishlash.
- **📄 Multimodal hujjatlar:** PDF, Word (DOCX), Excel (XLSX), matn va rasmlar (2 MB gacha).
- **👑 Admin paneli:** Telegram ID `7197666892` uchun statistika, so'nggi suhbatlar va jonli bildirishnomalar.
- **🌐 24/7 Render Mosligi:** Render Web Service portini ochib beruvchi o'rnatilgan HTTP server mavjud.

---

## 🚀 Render.com serverida 24/7 ishga tushirish yo'riqnomasi

### 1-qadam: GitHub ga yuklash
Terminalda quyidagi buyruqlarni bajaring:
```bash
git add .
git commit -m "Render 24/7 moslashuvi"
git branch -M main
git remote add origin https://github.com/miuceo/telegram-ai-bot.git
git push -u origin main
```

### 2-qadam: Render.com da yangi servis ochish
1. [render.com](https://render.com) saytiga kiring va profilingizga kiring.
2. **"New +"** tugmasini bosing va **"Web Service"** ni tanlang.
3. GitHub hisobingizni ulab, `telegram-ai-bot` repozitoriyasini tanlang (**Connect**).
4. Quyidagi parametrlarni to'ldiring:
   - **Name:** `telegram-ai-bot`
   - **Region:** `Frankfurt (EU Central)` yoki `Singapore`
   - **Branch:** `main`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
   - **Instance Type:** `Free`

### 3-qadam: Muhit o'zgaruvchilari (Environment Variables)
Sahifaning pastrog'idagi **"Environment Variables"** bo'limida quyidagi kalitlarni kiriting:
- `BOT_TOKEN` = `sizning_bot_tokeningiz`
- `GEMINI_API_KEY` = `sizning_gemini_api_kalitingiz`
- `GEMINI_MODEL` = `gemini-3.5-flash-lite`
- `ADMIN_ID` = `7197666892`
- `PORT` = `10000`

So'ngra **"Deploy Web Service"** tugmasini bosing.

Render loyihani yig'adi va sizga veb-manzil beradi (masalan: `https://telegram-ai-bot-xxxx.onrender.com`).

---

## ⏰ Cron Job orqali 24/7 rejimini yoqish (Uxlashning oldini olish)

Render Free tarifida har 15 daqiqada so'rov kelmasa, server uyqu holatiga o'tadi. Buni oldini olish va botni **24/7 tinimsiz** ishlatish uchun:

1. [cron-job.org](https://cron-job.org) saytiga kiring (bepul ro'yxatdan o'ting).
2. **"CREATE CRONJOB"** tugmasini bosing.
3. Sozlamalarni kiriting:
   - **Title:** `Telegram AI Bot Ping`
   - **URL:** Render bergan manzilingiz (masalan: `https://telegram-ai-bot-xxxx.onrender.com/health`)
   - **Schedule:** `Every 5 minutes` (Har 5 daqiqada)
4. **"CREATE"** tugmasini bosing.

Endi cron-job har 5 daqiqada serverga so'rov yuborib turadi va server hech qachon o'chmaydi (24/7 rejimida ishlaydi).
