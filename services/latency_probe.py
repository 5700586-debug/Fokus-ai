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
        note_pool_acquire(time.monotonic() - start)


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
            f"handler_total_ms={handler_total_ms}",
            flush=True,
        )
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            _active.set(None)
        except Exception:  # noqa: BLE001
            pass


# ----------------------------------------------------------------------------------------------
# HANDLER_METRICS — HAR BIR ishlov berilgan message/callback handler uchun bitta log qatori.
#
# Mavjud ``LATENCY_PROBE`` (faqat sinovchi uchun, beshta oqim) O'ZGARMAGAN. Quyidagi hisoblagichlar
# alohida ``ContextVar``da (parallel Update'lar aralashmaydi) va FAQAT shu qatorni to'ldiradi; mavjud
# hook'lar (``time_db_connect``/``db_execute``/``db_finish``) bir chaqiruvda ikkala hisobni alohida
# yuritadi, bitta o'lchovni ikki marta qo'shmaydi.
#
# Ma'nolari (HECH QAYERDA "tugma bosilgandan beri" EMAS):
#   total_ms       — ``dp.message``/``dp.callback_query`` outer middleware'ga KIRISHDAN (update-darajasidagi
#                    middleware'lar va FSM/event-isolation navbatidan KEYIN) qaytguncha: filtrlar, handler va menyu
#                    tozalash kiradi. Telegram'dan kelish va FSM navbati KIRMAYDI. Handler mos kelmasa qator yo'q.
#   db_queries     — bajarilgan SQL ``execute`` chaqiruvlari soni. ``executemany`` va ``executescript`` BITTA
#                    chaqiruv hisoblanadi. Postgres'da ``INSERT``dan keyingi ichki ``SELECT lastval()`` ham
#                    haqiqiy tarmoq qatnovi bo'lgani uchun alohida sanaladi. commit/rollback SONGA QO'SHILMAYDI.
#   db_ms          — execute + commit + rollback vaqtlari yig'indisi (har biri bir marta). Pool'dan ulanish
#                    olish vaqti KIRMAYDI (``pool_ms`` alohida).
#   pool_acquires  — ``pool.getconn()`` (SQLite'da ``sqlite3.connect``) chaqiruvlari soni. Bu YANGI FIZIK ulanish
#                    degani EMAS: pool bo'sh ulanishni qayta ishlatadi; fizik ulanish ochilishi alohida o'lchanmaydi.
#   rollbacks/rollback_ms — ochiq ``rollback()`` chaqiruvlari soni va vaqti (``db_ms`` ICHIDA, qayta qo'shilmaydi). Python
#                    ``rollback()`` chaqiruvi har doim tarmoq qatnovi degani EMAS (psycopg2 tranzaksiya ochiq bo'lmasa
#                    serverga hech narsa yubormaydi). ``psycopg2`` pool'ining ichki ``putconn`` rollback'i kuzatilMAYDI.
#   telegram_ms    — Telegram API so'rovlari (``bot.session`` middleware) kutish vaqti yig'indisi.
#   outcome        — ok | error (handler istisno ko'tarsa; istisno o'zgarishsiz qayta ko'tariladi).
# Xabar matni, callback_data, SQL, parametrlar, foydalanuvchi ID/ismi va sirlar HECH QACHON yozilmaydi —
# faqat statik handler funksiya nomi va son qiymatlar.
# ----------------------------------------------------------------------------------------------


@dataclass
class _Metrics:
    db_queries: int = 0
    db_total: float = 0.0
    pool_acquires: int = 0
    pool_total: float = 0.0
    telegram_total: float = 0.0
    rollbacks: int = 0
    rollback_total: float = 0.0
    handler: str | None = None  # haqiqiy mos handler nomi (inner middleware o'rnatadi)


_metrics: ContextVar["_Metrics | None"] = ContextVar("fokus_handler_metrics", default=None)


def _add_metrics(**deltas: float) -> None:
    try:
        metrics = _metrics.get()
        if metrics is None:
            return
        for name, value in deltas.items():
            setattr(metrics, name, getattr(metrics, name) + value)
    except Exception:  # noqa: BLE001
        pass


@contextmanager
def db_execute():
    """Bitta SQL ``execute`` atrofida: ``LATENCY_PROBE`` (avvalgidek) va ``HANDLER_METRICS`` uchun bir marta."""
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        try:
            state = _active.get()
            if state is not None:
                state.db_query_total += elapsed
                state.db_queries += 1
        except Exception:  # noqa: BLE001
            pass
        _add_metrics(db_queries=1, db_total=elapsed)


@contextmanager
def db_finish(legacy: bool = True, rollback: bool = False):
    """``commit()``/``rollback()`` atrofida: vaqt ``db_ms``ga bir marta qo'shiladi, ``db_queries``ga QO'SHILMAYDI.
    ``legacy=True`` — ``LATENCY_PROBE`` avvalgidek commit'ni so'rov deb sanashda davom etadi. ``rollback=True`` —
    shu vaqt ``rollbacks``/``rollback_ms``ga ham yoziladi (``db_ms`` ichida qoladi, qo'shimcha qo'shilmaydi)."""
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        if legacy:
            try:
                state = _active.get()
                if state is not None:
                    state.db_query_total += elapsed
                    state.db_queries += 1
            except Exception:  # noqa: BLE001
                pass
        _add_metrics(db_total=elapsed)
        if rollback:
            _add_metrics(rollbacks=1, rollback_total=elapsed)


def note_pool_acquire(elapsed: float = 0.0) -> None:
    _add_metrics(pool_acquires=1, pool_total=elapsed)


def note_telegram(elapsed: float) -> None:
    _add_metrics(telegram_total=elapsed)


async def telegram_request_middleware(make_request, bot, method):
    """``bot.session.middleware(...)``: Telegram API so'rovi kutish vaqtini ``telegram_ms``ga qo'shadi."""
    start = time.monotonic()
    try:
        return await make_request(bot, method)
    finally:
        note_telegram(time.monotonic() - start)


def _handler_name(data: dict) -> str:
    try:
        callback = data["handler"].callback
        name = getattr(callback, "__name__", None) or getattr(getattr(callback, "func", None), "__name__", None)
        return name or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


async def name_handler(handler, event, data: dict):
    """INNER middleware (``dp.message.middleware``): filtrlar handlerni tanlagandan KEYIN ishlaydi, shuning uchun
    ``data["handler"]`` haqiqiy mos handler (outer middleware'da u hali Dispatcher'ning ``_listen_update``i bo'ladi).
    Faqat statik funksiya nomini yozadi."""
    try:
        metrics = _metrics.get()
        if metrics is not None:
            metrics.handler = _handler_name(data)
    except Exception:  # noqa: BLE001
        pass
    return await handler(event, data)


async def measure_handler(kind: str, handler, event, data: dict):
    """``dp.message``/``dp.callback_query`` OUTER middleware: hisoblagichlarni boshlaydi; handler tugagach (agar
    haqiqiy handler mos kelgan bo'lsa — ``name_handler`` nomni yozgan) bitta ``HANDLER_METRICS`` qatori yozadi.
    ``total_ms`` outer middleware'ga kirishdan (update-darajasidagi middleware'lar va FSM navbatidan KEYIN)
    qaytguncha: marshrutlash/filtrlar, handler va menyu tozalash kiradi. Handler mos kelmasa qator yozilmaydi.
    O'lchov xatosi oqimni buzmaydi; handler istisnosi o'zgarishsiz qayta ko'tariladi; ContextVar ``finally``da tiklanadi."""
    try:
        from config import HANDLER_METRICS_ENABLED

        enabled = HANDLER_METRICS_ENABLED and _metrics.get() is None  # ichma-ich bo'lsa ikki marta sanalmasin
    except Exception:  # noqa: BLE001
        enabled = False
    if not enabled:
        return await handler(event, data)

    token = _metrics.set(_Metrics())
    metrics = _metrics.get()
    started = time.monotonic()
    outcome = "ok"
    try:
        return await handler(event, data)
    except BaseException:
        outcome = "error"
        raise
    finally:
        try:
            if metrics.handler is not None:
                print(
                    "HANDLER_METRICS "
                    f"handler={metrics.handler} kind={kind} total_ms={_ms(time.monotonic() - started)} "
                    f"db_queries={metrics.db_queries} db_ms={_ms(metrics.db_total)} "
                    f"pool_acquires={metrics.pool_acquires} pool_ms={_ms(metrics.pool_total)} "
                    f"rollbacks={metrics.rollbacks} rollback_ms={_ms(metrics.rollback_total)} "
                    f"telegram_ms={_ms(metrics.telegram_total)} outcome={outcome}",
                    flush=True,
                )
        except Exception:  # noqa: BLE001
            pass
        try:
            _metrics.reset(token)
        except Exception:  # noqa: BLE001
            try:
                _metrics.set(None)
            except Exception:  # noqa: BLE001
                pass
