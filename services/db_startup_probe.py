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
import time

SAMPLES = 7


def _fmt(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.1f}" for value in values) + "]"


def _probe_sync(connect) -> str:
    """Sinxron o'lchov (alohida oqimda chaqiriladi). Qaytaradi: yakuniy log qatori (exception ko'tarmaydi)."""
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


async def run_once(connect=None) -> None:
    """Bitta fon o'lchovi: sozlama o'chiq yoki Postgres bo'lmasa hech narsa qilmaydi. Hech qachon exception ko'tarmaydi."""
    try:
        import config
        import db

        if not config.DB_STARTUP_PROBE_ENABLED or not db._DATABASE_URL:
            return
        if connect is None:
            connect = db.get_connection
        line = await asyncio.to_thread(_probe_sync, connect)
        print(line, flush=True)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        try:
            print("DB_STARTUP_PROBE outcome=error stage=run samples=0", flush=True)
        except Exception:  # noqa: BLE001
            pass


def start(loop_task_holder: list) -> None:
    """Fon vazifasini yaratadi va havolasini ``loop_task_holder``da saqlaydi (GC to'xtatmasin)."""
    try:
        loop_task_holder.append(asyncio.create_task(run_once(), name="db_startup_probe"))
    except Exception:  # noqa: BLE001
        pass


async def shutdown(loop_task_holder: list, timeout: float = 5.0) -> None:
    """To'xtashda vazifani xavfsiz yakunlaydi (pool yopilishidan OLDIN chaqiriladi)."""
    for task in loop_task_holder:
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except Exception:  # noqa: BLE001
            task.cancel()
        except asyncio.CancelledError:
            task.cancel()
    loop_task_holder.clear()
