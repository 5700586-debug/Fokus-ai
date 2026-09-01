"""FOKUS AI ish oqimi (masalan smena ochish/yopish) davomida yuborilgan
vaqtinchalik bot xabarlarini (``message_id``) kuzatish uchun — oqim
yakunlangach shu xabarlarni Telegram chatidan xavfsiz o'chirish
mumkin bo'lsin. Bu jadval faqat CHAT tozalash uchun, hech qanday
biznes ma'lumot saqlamaydi (smena/tafovut/xarajat va h.k. o'z
jadvallarida o'zgarishsiz qoladi).
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS bot_workflow_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow TEXT NOT NULL,
    workflow_key TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    sent_at TEXT NOT NULL
);
"""
