"""Saturn umumiy guruhidagi avtomatik postlar (ertalabki salom, kunlik
dashboard, foydali ma'lumot, kechqurungi xulosa) uchun tarix.

``saturn_posts_log`` ikki maqsadga xizmat qiladi: (1) AI matn
generatsiyasida oxirgi postlarni "buni takrorlama" konteksti sifatida
berish, (2) foydali ma'lumot (tip) bankidan navbat bilan, yaqinda
ishlatilganini takrorlamasdan tanlash. Bir xil kunga bir xil post ikki
marta yuborilmasligi (idempotentlik) ``services/notifications.send_once``
orqali ta'minlanadi — bu jadval faqat tarix/xilma-xillik uchun.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS saturn_posts_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_type TEXT NOT NULL,
    post_date TEXT NOT NULL,
    content TEXT NOT NULL,
    tip_key TEXT,
    created_at TEXT NOT NULL
);
"""
