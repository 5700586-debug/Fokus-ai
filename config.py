import os
import sys

# Konsol kodировkasi muhitga qarab turlicha bo'ladi (masalan ba'zi Windows
# konsollari cp1251/cp866) — shuning uchun log/print'dagi emoji va
# o'zbekcha belgilar tashqi sozlamaga (PYTHONIOENCODING, konsol kodировkasi)
# bog'liq bo'lmasdan har doim xatosiz chiqishi uchun stdout/stderr shu
# yerda, har qanday boshqa modul print() chaqirishidan oldin, UTF-8'ga
# majburlanadi. ``config`` deyarli barcha modullar tomonidan eng birinchi
# import qilinadigan modul bo'lgani uchun bu yerga qo'yilgan.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

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

# Saturn tonggi rasmli xabaridagi kichik ob-havo belgisi uchun — Open-Meteo
# (keyingi WEATHER_PROVIDER_ENABLED=true bo'lganda ishlatiladi) shahar
# nomini emas, lat/lon so'raydi, shuning uchun koordinata ham kerak.
# Standart qiymat — Qo'qon. Hech qanday maxfiy API kalit talab qilinmaydi
# (Open-Meteo ochiq/bepul), shuning uchun WEATHER_API_KEY bu yerga
# aloqador emas — kelajakda kalit talab qiladigan provayderga
# almashtirilsa, o'sha payt ishlatiladi.
SATURN_WEATHER_CITY = os.getenv("SATURN_WEATHER_CITY", "Qo'qon")
SATURN_WEATHER_LAT = float(os.getenv("SATURN_WEATHER_LAT") or "40.5286")
SATURN_WEATHER_LON = float(os.getenv("SATURN_WEATHER_LON") or "70.9425")

# Tonggi rasmdagi ob-havo "sahnasi" (fon) qaysi vizual kategoriyaga
# tushishini aniqlashda ishlatiladigan chegaralar (qarang
# services/saturn_weather_scene.py). O'zbekiston sharoiti uchun
# muvozanatli standart qiymatlar — muhit o'zgaruvchisi orqali
# sozlanadi, kodga hardcode qilinmaydi.
SATURN_WIND_THRESHOLD_KMH = float(os.getenv("SATURN_WIND_THRESHOLD_KMH") or "30")
SATURN_HOT_THRESHOLD_C = float(os.getenv("SATURN_HOT_THRESHOLD_C") or "33")

# Saturn'ning ASL logotip fayli hali repoga qo'shilmagan. Fayl qo'shilsa,
# shu yo'lga (masalan "assets/logo/saturn_logo.png", shaffof fon bilan)
# ishora qilinadi. Bo'sh yoki fayl topilmasa, rasmda soxta logotip
# o'ylab topilmaydi — oddiy "SATURN" yozuvi ishlatiladi (qarang
# services/saturn_image.py).
SATURN_LOGO_PATH = os.getenv("SATURN_LOGO_PATH")

# "Friendly phase" — Saturn guruhiga hozircha faqat mehribon/foydali
# mazmun yuboriladi (moliyaviy ko'rsatkich, KPI tanqidi, jarima YO'Q).
# Keyingi, qattiqroq nazorat bosqichi HALI QURILMAGAN — bu flag shu
# bosqichga o'tish qaroriga tayyor joy sifatida saqlanadi (hozircha
# faqat hujjatlashtirish/kelajak uchun o'qiladi, chunki "qattiqroq"
# muqobil kontent hali mavjud emas — uni o'zboshimchalik bilan yaratish
# so'ralmagan).
SATURN_FRIENDLY_PHASE = os.getenv("SATURN_FRIENDLY_PHASE", "true").lower() == "true"

# Kassa/ombor rasmlaridan raqam o'qish (OCR/vision) hali ulanmagan —
# NullVisionExtractionProvider ishlatiladi, bot doim qo'lda kiritishni
# so'raydi (providers/vision_extraction_provider.py).
VISION_EXTRACTION_ENABLED = os.getenv("VISION_EXTRACTION_ENABLED", "false").lower() == "true"
VISION_EXTRACTION_API_KEY = os.getenv("VISION_EXTRACTION_API_KEY")

# Scheduler'lar (masalan kunlik kalibratsiya savollari) shu vaqt zonasiga
# nisbatan ishlaydi — hardcode qilinmaydi, .env orqali o'zgartiriladi.
COMPANY_TIMEZONE = os.getenv("COMPANY_TIMEZONE", "Asia/Tashkent")
