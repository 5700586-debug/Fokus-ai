import os

# Test va production muhitini ajratish. "test" bo'lsa main.py TEST_BOT_TOKEN
# (BOT_TOKEN emas), db.py esa TEST_DATABASE_URL (DATABASE_URL emas) o'qiydi —
# ikkalasi ham BUTUNLAY BOSHQA muhit o'zgaruvchi NOMI, shuning uchun ikkalasi
# tasodifan bir joyga (masalan bitta .env'ga) yozilgan bo'lsa ham, bitta
# jarayon ikkinchisining tokeni/bazasiga hech qachon tegmaydi.
ENVIRONMENT = (os.getenv("ENVIRONMENT") or "production").strip().lower()
if ENVIRONMENT not in ("production", "test"):
    ENVIRONMENT = "production"

# Asoschi (Founder) Telegram user_id. Kodga hardcode qilinmaydi — Founder
# almashsa, kod o'zgarishi/qayta deploy shart bo'lmasin uchun .env/Render
# environment orqali boshqariladi. Standart qiymat — bot yaratilgandan
# beri ishlatib kelingan Founder ID (mavjud .env'da FOUNDER_ID yo'q bo'lsa
# ham prod ishlashda uzilish bo'lmasligi uchun).
FOUNDER_ID = int(os.getenv("FOUNDER_ID") or "34213422")

# Tashqi providerlar (SMS, ob-havo) hali ulanmagan. Flag'lar False bo'lsa
# (yoki .env'da yo'q bo'lsa), providers/ paketidagi Null* implementatsiyalar
# ishlatiladi — bot ular yo'qligida ham yiqilmaydi. Real provider
# ulanganda shu yerga credential o'zgaruvchisi qo'shiladi (hech qachon
# hardcode qilinmaydi).
SMS_PROVIDER_ENABLED = os.getenv("SMS_PROVIDER_ENABLED", "false").lower() == "true"
SMS_API_KEY = os.getenv("SMS_API_KEY")

WEATHER_PROVIDER_ENABLED = os.getenv("WEATHER_PROVIDER_ENABLED", "false").lower() == "true"
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

# Kassa/ombor rasmlaridan raqam o'qish (OCR/vision) hali ulanmagan —
# NullVisionExtractionProvider ishlatiladi, bot doim qo'lda kiritishni
# so'raydi (providers/vision_extraction_provider.py).
VISION_EXTRACTION_ENABLED = os.getenv("VISION_EXTRACTION_ENABLED", "false").lower() == "true"
VISION_EXTRACTION_API_KEY = os.getenv("VISION_EXTRACTION_API_KEY")

# Scheduler'lar (masalan kunlik kalibratsiya savollari) shu vaqt zonasiga
# nisbatan ishlaydi — hardcode qilinmaydi, .env orqali o'zgartiriladi.
COMPANY_TIMEZONE = os.getenv("COMPANY_TIMEZONE", "Asia/Tashkent")
