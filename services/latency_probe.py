"""Vaqtinchalik, faqat sinovchi (tester) uchun ishlaydigan vaqt o'lchash
zondi — production robot E2E'da kuzatilgan umumiy 14-24 soniyalik
kechikishni tashxislash uchun (qarang I/S "LATENCY ANALYSIS" vazifasi).

Faqat ``roles.E2E_TESTER_TELEGRAM_ID`` (7952886089) uchun faollashadi —
BOSHQA HAR QANDAY foydalanuvchi uchun bu moduldagi barcha funksiyalar
zudlik bilan hech narsa qilmasdan qaytadi: log yozilmaydi, botning
xatti-harakatiga ZARRA ham ta'sir qilmaydi.

``contextvars.ContextVar`` ishlatiladi (oddiy modul-darajasidagi
o'zgaruvchi EMAS) — shu orqali bir vaqtning o'zida (yoki tez ketma-ket)
qayta ishlangan turli Update'larning vaqt ma'lumoti hech qachon
aralashmaydi: har bir ``asyncio`` vazifasi/kontekst mustaqil nusxa oladi.

Faqat BESHTA kuzatiladigan oqim mavjud (chaqiruvchi joylarda
``mark_handler_entry(label=...)``ga uzatilgan qiymatlar): sinovsmena,
market_list_submit, list_confirm, xarid, sinovtugat. Boshqa hech qanday
buyruq/handler bu modulni chaqirmaydi, shuning uchun ular uchun HECH
QANDAY log yozilmaydi (``end_update`` faqat ``label`` o'rnatilgan
bo'lsagina chiqaradi).

Xavfsizlik: har bir jamoat funksiyasi o'z tanasini ``try/except
Exception: pass`` bilan o'raydi — bu moduldagi har qanday kutilmagan
xato botning haqiqiy ishlov berishiga (javob matni, DB yozuvi, xatolik
handleri, callback tartibi) hech qachon ta'sir qilmaydi. Hech qachon
xabar matni, mahsulot nomi, ``test_run_id``, token, credential, DSN
yoki xom exception matni log qilinmaydi — faqat ``label`` (buyruq/
handler nomi) va son qiymatlar.
"""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

# ``roles.E2E_TESTER_TELEGRAM_ID`` bilan ATAYLAB QAYTA YOZILGAN (import
# qilinmagan): ``roles.py`` IMPORT vaqtidayoq ``db.get_connection()``
# orqali ``allowed_users``ni o'qiydi (Postgres rejimida) -- agar bu
# modul ``roles``ni import qilsa, ``db_postgres.PgConnection.__init__``
# (bu modulni LOKAL/lazy import qiladi) uchun qayta kirishli (re-entrant)
# dumaloq import zanjiri hosil bo'lardi: PgConnection.__init__ ->
# latency_probe import -> roles import -> db.get_connection() ->
# IKKINCHI PgConnection.__init__ -> latency_probe hali TO'LIQ
# yuklanmagani uchun ``AttributeError``. Shu son o'zgarmas va
# ``roles.py``dagi bilan bir xil ekanini ``tests/test_latency_probe.py``
# tekshiradi.
_PROBE_USER_ID = 7952886089


@dataclass
class _ProbeState:
    dispatcher_entry: float
    label: str | None = None
    handler_entry: float | None = None
    db_connect_total: float = 0.0
    db_connections: int = 0
    db_query_total: float = 0.0
    db_queries: int = 0
    telegram_send_total: float = 0.0


_active: ContextVar["_ProbeState | None"] = ContextVar("fokus_latency_probe_active", default=None)


def _ms(seconds: float) -> int:
    return int(round(seconds * 1000))


def begin_update(user_id: int | None) -> None:
    """Eng tashqi (dispatcher darajasidagi) middleware'da, marshrutlash
    boshlanishidan OLDIN, HAR BIR Update uchun chaqiriladi. Faqat aniq
    belgilangan sinovchi ID uchun yangi holat boshlaydi — boshqa hamma
    uchun (yoki xato holatida) faollikni tozalaydi, shuning uchun
    oldingi Update'dan qolgan holat hech qachon keyingisiga sizib
    o'tmaydi."""
    try:
        if user_id != _PROBE_USER_ID:
            _active.set(None)
            return
        _active.set(_ProbeState(dispatcher_entry=time.monotonic()))
    except Exception:  # noqa: BLE001
        try:
            _active.set(None)
        except Exception:  # noqa: BLE001
            pass


def mark_handler_entry(label: str) -> None:
    """Kuzatiladigan beshta oqimning har birida ANIQ birinchi qator
    sifatida chaqiriladi. ``label`` FAQAT buyruq/handler nomi bo'lishi
    kerak — xabar matni, mahsulot nomi yoki foydalanuvchi ma'lumoti
    hech qachon shu yerga uzatilmasin."""
    try:
        state = _active.get()
        if state is None:
            return
        state.handler_entry = time.monotonic()
        state.label = label
    except Exception:  # noqa: BLE001
        pass


@contextmanager
def time_db_connect():
    """``psycopg2.connect()`` atrofida — faqat vaqtni o'lchaydi, hech
    qanday xatti-harakatni o'zgartirmaydi (asl istisno bo'lsa ham
    o'zgarishsiz tarqaladi)."""
    start = time.monotonic()
    try:
        yield
    finally:
        try:
            state = _active.get()
            if state is not None:
                state.db_connect_total += time.monotonic() - start
                state.db_connections += 1
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def time_db_query():
    """Bitta ``cursor.execute()``/``conn.commit()`` atrofida —
    ``db_query_ms``/``db_queries`` shu ikkalasini birgalikda
    hisoblaydi (talab qilingan log formatida alohida commit maydoni
    yo'q)."""
    start = time.monotonic()
    try:
        yield
    finally:
        try:
            state = _active.get()
            if state is not None:
                state.db_query_total += time.monotonic() - start
                state.db_queries += 1
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def time_telegram_send():
    """Bitta Telegram javob yuborish chaqiruvi (``message.answer``/
    ``callback.answer``/``edit_reply_markup`` va h.k.) atrofida —
    bitta handler ichida bir nechta chaqiruv bo'lsa, yig'indi
    hisoblanadi."""
    start = time.monotonic()
    try:
        yield
    finally:
        try:
            state = _active.get()
            if state is not None:
                state.telegram_send_total += time.monotonic() - start
        except Exception:  # noqa: BLE001
            pass


def end_update() -> None:
    """Eng tashqi middleware'da ``handler(event, data)`` qaytgandan
    (ya'ni javob(lar) allaqachon yuborilgandan) KEYIN chaqiriladi. Agar
    shu Update davomida kuzatiladigan beshta oqimdan biri ham
    ``mark_handler_entry`` chaqirmagan bo'lsa (masalan sinovchi boshqa,
    kuzatilmaydigan buyruq yuborgan), HECH QANDAY log yozilmaydi —
    faqat holat tozalanadi."""
    try:
        state = _active.get()
        if state is None or state.label is None:
            return

        now = time.monotonic()
        queue_ms = (
            _ms(state.handler_entry - state.dispatcher_entry)
            if state.handler_entry is not None
            else "unmeasured"
        )
        handler_total_ms = (
            _ms(now - state.handler_entry) if state.handler_entry is not None else "unmeasured"
        )

        print(
            "LATENCY_PROBE "
            f"label={state.label} "
            f"queue_ms={queue_ms} "
            f"db_connect_ms={_ms(state.db_connect_total)} "
            f"db_query_ms={_ms(state.db_query_total)} "
            f"db_connections={state.db_connections} "
            f"db_queries={state.db_queries} "
            f"telegram_send_ms={_ms(state.telegram_send_total)} "
            f"handler_total_ms={handler_total_ms}"
        )
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            _active.set(None)
        except Exception:  # noqa: BLE001
            pass
