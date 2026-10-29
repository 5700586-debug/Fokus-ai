"""S2 — rasm-dalil: minus uchun rasm majburiy, 0 ball uchun ixtiyoriy; faqat Telegram file_id saqlanadi."""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiogram.methods import SendPhoto

import company_time
import evidence_handlers
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from db import get_connection
from services import discipline
from tests.bot_harness import send, send_callback

pytestmark = pytest.mark.anyio

NAZ, EMP, OTHER_NAZ = 1, 111, 2
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _daytime_clock(monkeypatch):
    # Ish kuni 06:00 da almashadi; testlar har doim kunduzgi barqaror vaqtda ishlaydi.
    fixed = company_time.now().replace(hour=12, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(company_time, "now", lambda: fixed)


def _setup(monkeypatch, main) -> None:
    import employees
    from roles import set_role

    set_role(NAZ, "nazoratchi", set_by=FOUNDER_ID)
    set_role(OTHER_NAZ, "nazoratchi", set_by=FOUNDER_ID)
    set_role(EMP, "kassir", set_by=FOUNDER_ID)
    employees.submit_profile(
        EMP, {"familiya": "Karimov", "ism": "Vali", "branch": RECRUITING_BRANCH_NAMES[0], "role_key": "kassir", "contacts": []}
    )
    employees.approve_profile(EMP, approved_by=FOUNDER_ID)
    discipline.add_rule(3, "Kechikish", "Ishga kechikish taqiqlanadi", created_by=FOUNDER_ID)

    async def fake_create(**kwargs):
        return SimpleNamespace(output_text="✅ Mos keladi.")

    monkeypatch.setattr(main.openai_client.responses, "create", fake_create)


def _bank() -> int:
    return discipline.get_salary(EMP)["bonus_bank"]


def _penalties() -> list[dict]:
    conn = get_connection()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM discipline_penalties WHERE employee_id = ?", (EMP,)).fetchall()]
    finally:
        conn.close()


async def _stage_minus(main, bot, actor: int = NAZ):
    await send_callback(main.dp, bot, actor, data=f"bos:pen:{EMP}:20", target_chat_id=actor)
    return await send(main.dp, bot, actor, text="3-nizom")


# ------------------------------------------------------------ strukturaviy --


def test_bot_handlers_never_call_apply_penalty_directly():
    """Minus faqat ``services.evidence_photo.apply_pending_penalty`` (rasm bilan) orqali yoziladi."""
    for name in ("discipline_bot.py", "nazoratchi_bot.py", "evidence_handlers.py"):
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "apply_penalty"
        ]
        assert calls == [], name


def test_apply_pending_penalty_rejects_missing_photo_and_foreign_supervisor():
    from services import evidence_photo

    pending = {"supervisor_id": NAZ, "employee_id": EMP, "rule_number": 3, "amount": 20, "penalty_date": "2026-10-30"}
    with pytest.raises(ValueError):
        evidence_photo.apply_pending_penalty(pending, NAZ, "")
    with pytest.raises(ValueError):
        evidence_photo.apply_pending_penalty(pending, OTHER_NAZ, "file-1")


# ------------------------------------------------------------------- minus --


async def test_minus_is_not_written_until_photo_and_then_written_once_with_file_id(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup(monkeypatch, main)

    sent = await _stage_minus(main, bot)
    assert any("dalil rasmini" in (getattr(m, "text", None) or "") for m in sent)
    assert _bank() == 0 and _penalties() == []

    sent = await send(main.dp, bot, NAZ, photo_file_id="ev-file-1")
    assert _bank() == -20
    rows = _penalties()
    assert len(rows) == 1 and rows[0]["evidence_file_id"] == "ev-file-1"
    photos = [m for m in sent if isinstance(m, SendPhoto) and m.chat_id == EMP]
    assert len(photos) == 1 and photos[0].photo == "ev-file-1" and "-20 ball" in photos[0].caption

    await send(main.dp, bot, NAZ, photo_file_id="ev-file-2")  # takroriy rasm
    assert _bank() == -20 and len(_penalties()) == 1


async def test_text_instead_of_photo_cancels_and_writes_nothing(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup(monkeypatch, main)
    await _stage_minus(main, bot)

    sent = await send(main.dp, bot, NAZ, text="rasm keyin")
    assert any("bekor qilindi" in (getattr(m, "text", None) or "") for m in sent)
    await send(main.dp, bot, NAZ, photo_file_id="late-photo")
    assert _bank() == 0 and _penalties() == []


async def test_cancel_button_clears_pending_minus(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup(monkeypatch, main)
    await _stage_minus(main, bot)

    await send_callback(main.dp, bot, NAZ, data=evidence_handlers.CB_CANCEL, target_chat_id=NAZ)
    await send(main.dp, bot, NAZ, photo_file_id="late-photo")
    assert _bank() == 0 and _penalties() == []


async def test_expired_pending_minus_is_not_applied(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup(monkeypatch, main)
    await _stage_minus(main, bot)

    real_time = evidence_handlers.time.time
    monkeypatch.setattr(evidence_handlers.time, "time", lambda: real_time() + evidence_handlers.PENDING_TTL_SECONDS + 1)
    await send(main.dp, bot, NAZ, photo_file_id="late-photo")
    assert _bank() == 0 and _penalties() == []


async def test_employee_notice_caption_is_limited_and_keeps_buttons():
    class _Bot:
        def __init__(self):
            self.calls = []

        async def send_photo(self, chat_id, photo, caption=None, reply_markup=None):
            self.calls.append((chat_id, photo, caption, reply_markup))

    bot = _Bot()
    marker = object()
    await evidence_handlers.send_evidence_notice(bot, EMP, "f1", "x" * 2000, reply_markup=marker)
    assert bot.calls == [(EMP, "f1", "x" * 1024, marker)]


# -------------------------------------------------------------- 0 ball rasmi --


async def _zero_grade(main, bot):
    ymd = company_time.today().strftime("%Y%m%d")
    return await send_callback(
        main.dp, bot, NAZ, data=f"bos:grade:{EMP}:{discipline.GRADE_BAJARILMAGAN}:{ymd}", target_chat_id=NAZ
    )


def _evidence_of_today() -> str | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT evidence_file_id FROM daily_evaluations WHERE employee_id = ? AND eval_date = ?",
            (EMP, company_time.today().isoformat()),
        ).fetchone()
        return row["evidence_file_id"] if row else None
    finally:
        conn.close()


async def test_zero_grade_is_saved_immediately_and_optional_photo_is_attached(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup(monkeypatch, main)

    sent = await _zero_grade(main, bot)
    assert discipline.get_daily_grade(EMP, company_time.today().isoformat())["grade_points"] == 0
    assert any("ixtiyoriy" in (getattr(m, "text", None) or "") for m in sent)

    sent = await send(main.dp, bot, NAZ, photo_file_id="zero-photo")
    assert _evidence_of_today() == "zero-photo"
    assert any(isinstance(m, SendPhoto) and m.chat_id == EMP and m.photo == "zero-photo" for m in sent)


async def test_zero_grade_photo_can_be_skipped(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup(monkeypatch, main)
    await _zero_grade(main, bot)

    await send_callback(main.dp, bot, NAZ, data=evidence_handlers.CB_SKIP, target_chat_id=NAZ)
    await send(main.dp, bot, NAZ, photo_file_id="late-photo")
    assert _evidence_of_today() is None
    assert discipline.get_daily_grade(EMP, company_time.today().isoformat())["grade_points"] == 0


async def test_zero_grade_photo_not_attached_after_grade_was_changed(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup(monkeypatch, main)
    await _zero_grade(main, bot)
    discipline.record_daily_grade(EMP, NAZ, company_time.today().isoformat(), discipline.GRADE_ALO)

    await send(main.dp, bot, NAZ, photo_file_id="zero-photo")
    assert _evidence_of_today() is None


async def test_no_photo_prompt_for_other_grades(bot_dp, monkeypatch):
    main, bot = bot_dp
    _setup(monkeypatch, main)
    ymd = company_time.today().strftime("%Y%m%d")
    sent = await send_callback(main.dp, bot, NAZ, data=f"bos:grade:{EMP}:{discipline.GRADE_ALO}:{ymd}", target_chat_id=NAZ)
    assert not any("ixtiyoriy" in (getattr(m, "text", None) or "") for m in sent)
