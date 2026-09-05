"""Vaqtinchalik ``services/latency_probe.py`` zondi uchun maqsadli
testlar — faqat sinovchi (``roles.E2E_TESTER_TELEGRAM_ID``) uchun
log yozilishini, bir vaqtda kelgan yangilanishlar vaqt ma'lumotini
aralashtirmasligini, mavjud besh oqimning javob/DB natijasi
o'zgarmaganini, zond ichidagi kutilmagan xato handlerni buzmasligini
va logda hech qachon xabar matni/mahsulot nomi/maxfiy ma'lumot
chiqmasligini tekshiradi.
"""

import asyncio

import pytest

import company_time
import roles
from config import FOUNDER_ID
from repositories import cash_shifts as cash_shifts_repo
from repositories import shift_deficiencies as shift_deficiencies_repo
from tests.bot_harness import send, send_callback, texts

pytestmark = pytest.mark.anyio

_TESTER_ID = roles.E2E_TESTER_TELEGRAM_ID
_PROBE_FIELDS = (
    "queue_ms=",
    "db_connect_ms=",
    "db_query_ms=",
    "db_connections=",
    "db_queries=",
    "telegram_send_ms=",
    "handler_total_ms=",
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_taminotchi(user_id: int) -> None:
    from roles import set_role

    set_role(user_id, "taminotchi", set_by=FOUNDER_ID)


def _probe_lines(captured_out: str) -> list[str]:
    return [line for line in captured_out.splitlines() if line.startswith("LATENCY_PROBE")]


def test_probe_user_id_constant_matches_roles_e2e_tester_id():
    """``services/latency_probe.py`` ``roles.E2E_TESTER_TELEGRAM_ID``ni
    IMPORT qilmaydi (dumaloq import xatosining oldini olish uchun,
    qarang shu modul faylidagi izoh) — shuning uchun qiymat qo'lda
    qayta yozilgan. Ikkalasi bir-biridan uzoqlashib qolmasligi uchun
    shu tenglik alohida tekshiriladi."""
    from services import latency_probe

    assert latency_probe._PROBE_USER_ID == roles.E2E_TESTER_TELEGRAM_ID


async def test_non_tester_produces_no_latency_probe_logs(bot_dp, capsys):
    main, bot = bot_dp
    _make_taminotchi(999999001)

    await send(main.dp, bot, 999999001, text="/xarid")

    out = capsys.readouterr().out
    assert _probe_lines(out) == []


async def test_tester_timings_remain_isolated_between_concurrent_updates(capsys):
    """Ikkita "yangilanish" bir vaqtda (``asyncio.gather``, orada
    ``asyncio.sleep(0)`` bilan ataylab kesishtirilgan) qayta ishlansa
    ham, ``contextvars.ContextVar`` tufayli har birining o'z
    ``label``/hisoblagichlari boshqasiga sizib o'tmasligi kerak."""
    from services import latency_probe

    async def _run(label: str, connect_calls: int) -> None:
        latency_probe.begin_update(_TESTER_ID)
        latency_probe.mark_handler_entry(label)
        await asyncio.sleep(0)
        for _ in range(connect_calls):
            with latency_probe.time_db_connect():
                pass
            await asyncio.sleep(0)
        latency_probe.end_update()

    await asyncio.gather(_run("concurrent_a", 1), _run("concurrent_b", 3))

    lines = _probe_lines(capsys.readouterr().out)
    line_a = next(line for line in lines if "label=concurrent_a" in line)
    line_b = next(line for line in lines if "label=concurrent_b" in line)
    assert "db_connections=1" in line_a
    assert "db_connections=3" in line_b


async def test_timer_failure_never_breaks_handler(bot_dp, monkeypatch):
    """Zond ichidagi HAR QANDAY kutilmagan xato (masalan ``ContextVar``
    o'zi portlab ketsa) haqiqiy handler javobiga ta'sir qilmasligi
    kerak — barcha jamoat funksiyalari o'z tanasini
    ``try/except Exception: pass`` bilan o'raganini tasdiqlaydi.
    ``ContextVar`` obyektining o'zi attribute-mutatsiyani qo'llab-
    quvvatlamagani uchun (C darajasida implementatsiya qilingan) butun
    modul darajasidagi ``_active`` nomi portlaydigan soxta obyektga
    almashtiriladi."""
    from services import latency_probe

    class _BoomingActive:
        def get(self, *args, **kwargs):
            raise RuntimeError("probe boom")

        def set(self, *args, **kwargs):
            raise RuntimeError("probe boom")

    monkeypatch.setattr(latency_probe, "_active", _BoomingActive())

    main, bot = bot_dp
    sent = await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    combined = " ".join(t for t in texts(sent) if t)
    assert "TEST smena boshlandi" in combined


async def test_probe_log_never_contains_message_content_or_secrets(bot_dp, capsys):
    main, bot = bot_dp

    await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    capsys.readouterr()  # yuqoridagi qadamni tashlab, faqat keyingisini tekshiramiz

    secret_marker = "SuperMaxfiyMahsulotNomi12345"
    await send(main.dp, bot, _TESTER_ID, text=f"{secret_marker} 5 kg\nKaram 2 dona")
    await send_callback(main.dp, bot, _TESTER_ID, data="csdef_list_confirm", target_chat_id=_TESTER_ID)

    out = capsys.readouterr().out
    probe_lines = _probe_lines(out)
    assert probe_lines, "kutilgan LATENCY_PROBE loglari topilmadi"

    combined_probe_output = "\n".join(probe_lines)
    assert secret_marker not in combined_probe_output
    assert "Karam" not in combined_probe_output
    assert "DATABASE_URL" not in combined_probe_output
    assert "postgres" not in combined_probe_output.lower()
    assert "token" not in combined_probe_output.lower()

    for line in probe_lines:
        assert line.startswith("LATENCY_PROBE label=")
        for field in _PROBE_FIELDS:
            assert field in line


async def test_instrumented_flows_preserve_existing_replies_and_db_rows(bot_dp):
    """Beshta kuzatiladigan oqimning har biri instrumentatsiyadan
    KEYIN ham AYNAN oldingi kabi javob matni va DB natijasi berishini
    tasdiqlaydi (qarang ``tests/test_e2e_test_isolation.py``dagi
    o'xshash mavjud testlar)."""
    main, bot = bot_dp

    sent = await send(main.dp, bot, _TESTER_ID, text="/sinovsmena")
    assert "TEST smena boshlandi" in " ".join(t for t in texts(sent) if t)

    sent = await send(main.dp, bot, _TESTER_ID, text="Pomidor 10 kg\nKaram 2 dona")
    combined = " ".join(t for t in texts(sent) if t)
    assert "Ro'yxat tayyor" in combined
    assert "Pomidor — 10 kg" in combined

    sent = await send_callback(main.dp, bot, _TESTER_ID, data="csdef_list_confirm", target_chat_id=_TESTER_ID)
    assert "✅ TEST: 2 ta mahsulot qo'shildi" in " ".join(t for t in texts(sent) if t)

    today = company_time.today().isoformat()
    shift = cash_shifts_repo.get_open_test_shift(_TESTER_ID, today)
    assert shift is not None
    items = shift_deficiencies_repo.get_test_market_items(shift["test_run_id"])
    assert {i["product_name"] for i in items} == {"Pomidor", "Karam"}

    sent = await send(main.dp, bot, _TESTER_ID, text="/xarid")
    xarid_text = " ".join(t for t in texts(sent) if t)
    assert "Pomidor" in xarid_text and "Karam" in xarid_text

    sent = await send(main.dp, bot, _TESTER_ID, text="/sinovtugat")
    assert "yakunlandi va tozalandi" in " ".join(t for t in texts(sent) if t)

    sent = await send(main.dp, bot, _TESTER_ID, text="/xarid")
    assert "Faol TEST yugurish topilmadi" in " ".join(t for t in texts(sent) if t)
