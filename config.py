import os

FOUNDER_ID = 34213422

# Tashqi providerlar (SMS, ob-havo) hali ulanmagan. Flag'lar False bo'lsa
# (yoki .env'da yo'q bo'lsa), providers/ paketidagi Null* implementatsiyalar
# ishlatiladi — bot ular yo'qligida ham yiqilmaydi. Real provider
# ulanganda shu yerga credential o'zgaruvchisi qo'shiladi (hech qachon
# hardcode qilinmaydi).
SMS_PROVIDER_ENABLED = os.getenv("SMS_PROVIDER_ENABLED", "false").lower() == "true"
SMS_API_KEY = os.getenv("SMS_API_KEY")

WEATHER_PROVIDER_ENABLED = os.getenv("WEATHER_PROVIDER_ENABLED", "false").lower() == "true"
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
