"""Bot ishga tushganda BIR MARTALIK fon "SELECT 1" o'lchovi — minimal DB qatnovining taxminiy narxini ko'rish uchun.

Qanday ishlaydi: mavjud pool orqali bitta ulanish olinadi (``PgConnection``), 1 ta qizdirish + 7 ta ketma-ket ``SELECT 1``
bajariladi (har safar natija ``1`` ekani tekshiriladi), oxirida ochiq ``rollback()`` va ulanish pool'ga qaytariladi
(``finally``). Hammasi alohida oqimda (``asyncio.to_thread``) — event loop, Telegram polling va javoblar kutmaydi.
Bitta yakuniy log qatori: ``DB_STARTUP_PROBE ...``. Xatoda ham bitta xavfsiz qator (faqat bosqich nomi: exception matni,
SQL, DSN, parametr, ID yoki sir yozilmaydi). Davriy qayta urinish yo'q. ``DB_STARTUP_PROBE_ENABLED=0`` o'chiradi.

Ma'nolari (HECH BIRI sof tarmoq RTT'si EMAS):
  - ``first_execute_ms`` — qizdirish ``SELECT 1``: psycopg2 birinchi ``execute``da ``BEGIN``ni ham yuboradi, shuning
    uchun bu qiymatga BEGIN xarajati kirishi mumkin;
  - ``sample_ms`` — keyingi 7 ta iliq ``SELECT 1`` (har biri — minimal DB qatnovining taxminiy narxi: tarmoq + server +
    psycopg2 ishi; sof RTT emas), ``min/median/max`` shulardan;
  - ``pool_ms`` — ``PgConnection`` ochish (``pool.getconn``; bo'sh ulanish bo'lmasa yangi fizik ulanish ochilishi mumkin);
  - ``rollback_ms`` — yakuniy ochiq ``rollback()`` (tranzaksiya ochiq bo'lgani uchun serverga yuboriladi).
Bu o'lchov oddiy handler metrikalariga (``HANDLER_METRICS``) aralashmaydi: u ``ContextVar`` faol bo'lmagan fon oqimida
ishlaydi. Faqat Render jarayonining o'zida ishlaganda Render natijasi bo'ladi; boshqa serverdagi o'lchov Render natijasi emas."""

import asyncio
import statistics
import threading
import time
from dataclasses import dataclass, field

SAMPLES = 7


def _fmt(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.1f}" for value in values) + "]"


def _probe_sync(connect, done: threading.Event | None = None) -> str:
    """Sinxron o'lchov (alohida oqimda chaqiriladi). Qaytaradi: yakuniy log qatori (exception ko'tarmaydi).
    ``done`` berilsa, ulanish ``finally``da qaytarilgandan KEYIN o'rnatiladi: shutdown shu belgi bo'yicha oqim HAQIQATAN
    tugaganini biladi (asyncio task'ining bekor bo'lishi oqimni to'xtatmaydi)."""
    try:
        return _probe_body(connect)
    finally:
        if done is not None:
            done.set()


def _probe_body(connect) -> str:
    from services import latency_probe

    # Bu oqim kontekst nusxasini oladi: agar chaqiruvchida HANDLER_METRICS/LATENCY_PROBE faol bo'lsa ham, bu
    # o'lchov ularga qo'shilmasin (oddiy handler metrikalariga aralashmaydi).
    latency_probe._metrics.set(None)
    latency_probe._active.set(None)
    stage = "pool"
    conn = None
    samples: list[float] = []
    pool_ms = first_ms = rollback_ms = 0.0
    try:
        started = time.perf_counter()
        conn = connect()
        pool_ms = (time.perf_counter() - started) * 1000

        stage = "execute"
        for index in range(SAMPLES + 1):
            started = time.perf_counter()
            row = conn.execute("SELECT 1 AS one").fetchone()
            elapsed = (time.perf_counter() - started) * 1000
            if row is None or row["one"] != 1:
                stage = "verify"
                raise ValueError("kutilmagan natija")
            if index == 0:
                first_ms = elapsed
            else:
                samples.append(elapsed)

        stage = "rollback"
        started = time.perf_counter()
        conn.rollback()
        rollback_ms = (time.perf_counter() - started) * 1000
        outcome = "ok"
    except Exception:  # noqa: BLE001
        outcome = f"error stage={stage}"
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    if outcome == "ok" and samples:
        return (
            f"DB_STARTUP_PROBE outcome=ok samples={len(samples)} sample_ms={_fmt(samples)} "
            f"min_ms={min(samples):.1f} median_ms={statistics.median(samples):.1f} max_ms={max(samples):.1f} "
            f"first_execute_ms={first_ms:.1f} pool_ms={pool_ms:.1f} rollback_ms={rollback_ms:.1f}"
        )
    return (
        f"DB_STARTUP_PROBE outcome={outcome if outcome != 'ok' else 'error stage=execute'} samples={len(samples)} "
        f"sample_ms={_fmt(samples)} pool_ms={pool_ms:.1f} rollback_ms={rollback_ms:.1f}"
    )


@dataclass
class _Entry:
    """Fon o'lchovining ikkala tomoni: asyncio ``task`` VA haqiqiy oqim tugaganini bildiruvchi ``done`` belgisi."""

    task: "asyncio.Task"
    done: threading.Event = field(default_factory=threading.Event)
    started: threading.Event = field(default_factory=threading.Event)  # oqim ishga tushirildimi


async def run_once(connect=None, done: threading.Event | None = None, started: threading.Event | None = None) -> None:
    """Bitta fon o'lchovi: sozlama o'chiq yoki Postgres bo'lmasa hech narsa qilmaydi. Hech qachon exception ko'tarmaydi
    (faqat ``CancelledError`` qayta ko'tariladi). ``done`` — oqim ishlamagan bo'lsa shu yerda, ishlagan bo'lsa oqimning
    o'zida (ulanish qaytgandan keyin) o'rnatiladi."""
    thread_started = False
    try:
        import config
        import db

        if not config.DB_STARTUP_PROBE_ENABLED or not db._DATABASE_URL:
            return
        if connect is None:
            connect = db.get_connection
        thread_started = True
        if started is not None:
            started.set()
        line = await asyncio.to_thread(_probe_sync, connect, done)
        print(line, flush=True)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        try:
            print("DB_STARTUP_PROBE outcome=error stage=run samples=0", flush=True)
        except Exception:  # noqa: BLE001
            pass
    finally:
        if done is not None and not thread_started:
            done.set()


def start(holder: list) -> None:
    """Fon vazifasini yaratadi; ``task`` havolasi va ``done`` belgisi ``holder``da ish TUGAGUNCHA saqlanadi."""
    try:
        entry = _Entry(task=None)  # type: ignore[arg-type]
        entry.task = asyncio.create_task(run_once(done=entry.done, started=entry.started), name="db_startup_probe")
        holder.append(entry)
    except Exception:  # noqa: BLE001
        pass


async def _wait_thread(done: threading.Event, limit: float) -> bool:
    """Oqim tugashini event loop'ni to'smasdan kutadi; ``CancelledError`` bu yerda kutishni to'xtatmaydi (qayta
    ko'tarish chaqiruvchida). Qaytaradi: oqim tugadimi."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit
    cancelled = False
    while not done.is_set() and loop.time() < deadline:
        try:
            await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            cancelled = True  # kutish davom etadi: pool oqim ishlayotganda yopilmasin
    if cancelled:
        raise asyncio.CancelledError()
    return done.is_set()


def _self_cancelled(entry_task: "asyncio.Task") -> bool:
    """``await`` paytida kelgan ``CancelledError`` — ``shutdown``ning O'ZI bekor qilinganidanmi (``True``) yoki kutilayotgan
    probe task'i bekor bo'lganidanmi (``False``)?"""
    current = asyncio.current_task()
    cancelling = getattr(current, "cancelling", None)  # Python 3.11+
    if cancelling is not None:
        return cancelling() > 0
    return not entry_task.cancelled()


async def shutdown(holder: list, timeout: float = 5.0, thread_timeout: float = 30.0) -> None:
    """To'xtashda (``close_all_pools()`` dan OLDIN chaqiriladi) o'lchovni xavfsiz yakunlaydi.

    Kutish chegaralari: (1) ``timeout`` — task o'zi tugashini kutish; keyin task bekor qilinadi. Task'ning bekor bo'lishi
    ``asyncio.to_thread`` ichidagi DB ishini TO'XTATMAYDI, shuning uchun (2) ``thread_timeout`` — oqim HAQIQATAN tugab,
    ulanish ``finally``da pool'ga qaytganini bildiruvchi ``done`` belgisini kutish (event loop to'silmaydi). Faqat shundan
    keyin ``holder`` tozalanadi va chaqiruvchi pool'ni yopadi. ``thread_timeout`` o'tib ham oqim tugamagan bo'lsa (juda
    kam holat) bu haqda bitta xavfsiz qator yoziladi va to'xtash davom etadi — oqim shu paytda ishlayotgan bo'lishi mumkin
    ("to'xtadi" deb hisoblanmaydi). ``shutdown`` o'zi bekor qilinsa, tozalash baribir oxirigacha bajariladi va
    ``CancelledError`` qayta ko'tariladi."""
    cancelled = False
    for entry in list(holder):
        try:
            await asyncio.wait_for(asyncio.shield(entry.task), timeout=timeout)
        except asyncio.TimeoutError:
            entry.task.cancel()
        except asyncio.CancelledError:
            cancelled = cancelled or _self_cancelled(entry.task)
            entry.task.cancel()
        except Exception:  # noqa: BLE001
            pass
        try:
            if entry.task.cancelled() or entry.task.done():
                pass
            else:
                try:
                    await asyncio.wait_for(asyncio.shield(entry.task), timeout=1.0)  # bekor qilingan task tugashini kut
                except asyncio.CancelledError:
                    # task'ning o'zi bekor bo'lgani ham, shutdown bekor qilingani ham shu yerga tushadi: ikkinchisini
                    # yutib yubormaslik uchun shunday belgilanadi (cleanup davom etadi, oxirida qayta ko'tariladi)
                    cancelled = cancelled or _self_cancelled(entry.task)
                except Exception:  # noqa: BLE001
                    pass
            if entry.task.done() and not entry.started.is_set():
                entry.done.set()  # oqim umuman ishga tushmagan (masalan, task birinchi qadamdan oldin bekor bo'lgan)
            finished = await _wait_thread(entry.done, thread_timeout)
            if not finished:
                print("DB_STARTUP_PROBE outcome=error stage=shutdown samples=0", flush=True)
        except asyncio.CancelledError:
            cancelled = True
    holder.clear()
    if cancelled:
        raise asyncio.CancelledError()
