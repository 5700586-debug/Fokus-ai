"""📱 Baholash ekrani: faqat imzolangan initData, faqat baholash ruxsati, sana serverda, chatdagi bilan bir xil yozuv/xabar,
takroriy bosish ikkinchi yozuv yaratmaydi, bajarilmagan uchun dalil rasmi chatda so'raladi."""

import hashlib
import hmac
import json
import os
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pytest
from aiogram.methods import SendMessage
from aiohttp import web
from aiohttp import test_utils

import company_time
import webapp_server
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES, SUPERVISION_GENERAL_BRANCH
from db import get_connection
from services import grading_webapp
from tests.bot_harness import send

pytestmark = pytest.mark.anyio

NAZ, CASHIER, DRIVER, OUTSIDER = 1, 901, 902, 903
FIXED = datetime(2026, 11, 3, 12, 0, tzinfo=ZoneInfo("Asia/Tashkent"))


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(company_time, "now", lambda: FIXED)
    grading_webapp._hits.clear()
    grading_webapp._photo_locks.clear()  # har test o'z event loop'ida


def _signed(user_id: int, token: str, auth_date: int | None = None) -> str:
    fields = {"auth_date": str(int(FIXED.timestamp()) if auth_date is None else auth_date),
              "user": json.dumps({"id": user_id})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return urlencode({**fields, "hash": hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()})


def _seed() -> None:
    from roles import set_role

    set_role(NAZ, "nazoratchi", set_by=FOUNDER_ID)
    set_role(DRIVER, "haydovchi", set_by=FOUNDER_ID)
    conn = get_connection()
    try:
        conn.execute("INSERT INTO employees (user_id, familiya, ism, branch, status, phone) "
                     "VALUES (?, 'Kassir', 'Vali', ?, 'approved', '+998900000000')", (CASHIER, RECRUITING_BRANCH_NAMES[0]))
        conn.execute("INSERT INTO employees (user_id, familiya, ism, branch, status) "
                     "VALUES (?, 'Haydovchi', 'Ali', NULL, 'approved')", (DRIVER,))
        conn.commit()
    finally:
        conn.close()


def _grades() -> list[dict]:
    conn = get_connection()
    try:
        return [dict(r) for r in conn.execute("SELECT employee_id, eval_date, grade_key FROM daily_evaluations").fetchall()]
    finally:
        conn.close()


def _token() -> str:
    return os.environ["BOT_TOKEN"]


def test_authenticate_rules():
    _seed()
    now = int(FIXED.timestamp())
    assert grading_webapp.authenticate(_signed(NAZ, _token()), _token(), now=now) == NAZ
    for bad, status in (
        (_signed(NAZ, "999:other"), 401),                       # boshqa bot imzosi
        (_signed(NAZ, _token(), auth_date=now - 3601), 401),   # 1 soatdan eski
        (_signed(OUTSIDER, _token()), 403),                     # baholash ruxsati yo'q
        ("", 401),
    ):
        with pytest.raises(grading_webapp.WebAppError) as error:
            grading_webapp.authenticate(bad, _token(), now=now)
        assert error.value.status == status


def test_rate_limit():
    for i in range(grading_webapp.RATE_LIMIT_PER_MINUTE):
        grading_webapp.check_rate(NAZ, now=100.0 + i)
    with pytest.raises(grading_webapp.WebAppError):
        grading_webapp.check_rate(NAZ, now=130.0)
    grading_webapp.check_rate(NAZ, now=200.0)


def test_day_payload_has_general_branch_and_no_private_fields():
    _seed()
    payload = grading_webapp.day_payload(NAZ)
    assert payload["work_date"] == "2026-11-03" and not payload["day_closed"]
    names = [b["name"] for b in payload["branches"]]
    assert names == [RECRUITING_BRANCH_NAMES[0], SUPERVISION_GENERAL_BRANCH]
    people = [e for b in payload["branches"] for e in b["employees"]]
    assert {e["id"] for e in people} == {CASHIER, DRIVER}
    assert set(people[0]) == {"id", "name", "status", "grade"}
    assert "+998" not in json.dumps(payload)


async def test_grade_saves_once_and_notifies_employee(bot_dp):
    main, bot = bot_dp
    _seed()
    bot.sent.clear()
    result = await grading_webapp.grade(bot, main.dp.storage, NAZ, CASHIER, "alo")
    assert result["ok"] and result["changed"]
    assert _grades() == [{"employee_id": CASHIER, "eval_date": "2026-11-03", "grade_key": "alo"}]
    assert any(isinstance(m, SendMessage) and m.chat_id == CASHIER and "Baho" in m.text for m in bot.sent)

    bot.sent.clear()
    again = await grading_webapp.grade(bot, main.dp.storage, NAZ, CASHIER, "alo")  # takroriy bosish / ikkinchi qurilma
    assert not again["changed"] and len(_grades()) == 1
    assert not any(isinstance(m, SendMessage) and m.chat_id == CASHIER for m in bot.sent)

    fixed = await grading_webapp.grade(bot, main.dp.storage, NAZ, CASHIER, "norma")  # tuzatish — chatdagi kabi
    assert fixed["changed"] and _grades()[0]["grade_key"] == "norma"


async def test_grade_rejects_bad_input_and_invisible_people(bot_dp):
    main, bot = bot_dp
    _seed()
    for employee_id, grade_key, status in ((CASHIER, "zo'r", 400), ("901", "alo", 400), (NAZ, "alo", 403),
                                           (FOUNDER_ID, "alo", 403), (424242, "alo", 403)):
        with pytest.raises(grading_webapp.WebAppError) as error:
            await grading_webapp.grade(bot, main.dp.storage, NAZ, employee_id, grade_key)
        assert error.value.status == status
    assert _grades() == []


async def test_branchless_employee_can_be_graded(bot_dp):
    main, bot = bot_dp
    _seed()
    assert (await grading_webapp.grade(bot, main.dp.storage, NAZ, DRIVER, "norma"))["ok"]
    assert _grades()[0]["employee_id"] == DRIVER


async def test_bajarilmagan_asks_optional_photo_in_chat(bot_dp):
    main, bot = bot_dp
    _seed()
    await (await _state(main, bot)).clear()  # boshqa testdan qolgan holat bo'lmasin
    bot.sent.clear()
    result = await grading_webapp.grade(bot, main.dp.storage, NAZ, CASHIER, "bajarilmagan")
    assert result["photo"] == grading_webapp.PHOTO_REQUESTED
    assert any(isinstance(m, SendMessage) and m.chat_id == NAZ and "Dalil rasmi" in m.text for m in bot.sent)
    sent = await send(main.dp, bot, NAZ, photo_file_id="photo-1")
    assert any(isinstance(m, SendMessage) and m.chat_id == NAZ and "Dalil saqlandi" in m.text for m in sent)


async def _state(main, bot):
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey

    return FSMContext(storage=main.dp.storage, key=StorageKey(bot_id=bot.id, chat_id=NAZ, user_id=NAZ))


async def test_second_bajarilmagan_does_not_steal_pending_photo(bot_dp):
    main, bot = bot_dp
    _seed()
    state = await _state(main, bot)
    await state.clear()
    first = await grading_webapp.grade(bot, main.dp.storage, NAZ, CASHIER, "bajarilmagan")
    second = await grading_webapp.grade(bot, main.dp.storage, NAZ, DRIVER, "bajarilmagan")
    assert first["photo"] == grading_webapp.PHOTO_REQUESTED and second["photo"] == grading_webapp.PHOTO_CHAT_BUSY
    assert (await state.get_data())["grade_pending"]["employee_id"] == CASHIER  # rasm birinchi xodimga bog'lanadi
    assert len(_grades()) == 2  # baholar baribir saqlangan
    await state.clear()


async def test_parallel_bajarilmagan_sets_only_one_pending(bot_dp):
    import asyncio

    main, bot = bot_dp
    _seed()
    state = await _state(main, bot)
    await state.clear()
    results = await asyncio.gather(grading_webapp.grade(bot, main.dp.storage, NAZ, CASHIER, "bajarilmagan"),
                                   grading_webapp.grade(bot, main.dp.storage, NAZ, DRIVER, "bajarilmagan"))
    assert sorted(r["photo"] for r in results) == [grading_webapp.PHOTO_CHAT_BUSY, grading_webapp.PHOTO_REQUESTED]
    requested = next(r for r in results if r["photo"] == grading_webapp.PHOTO_REQUESTED)
    assert (await state.get_data())["grade_pending"]["employee_id"] == requested["employee_id"]
    await state.clear()


async def test_busy_chat_flow_is_not_broken(bot_dp):
    main, bot = bot_dp
    _seed()
    import evidence_handlers

    state = await _state(main, bot)
    await state.clear()
    await state.set_state(evidence_handlers.EvidenceStates.waiting_photo)  # nazoratchi minus rasmini yuborayotgan
    await state.update_data(evidence_pending={"source": "x", "supervisor_id": NAZ})
    bot.sent.clear()
    result = await grading_webapp.grade(bot, main.dp.storage, NAZ, CASHIER, "bajarilmagan")
    assert result["ok"] and result["photo"] == grading_webapp.PHOTO_CHAT_BUSY
    assert await state.get_state() == evidence_handlers.EvidenceStates.waiting_photo.state
    assert (await state.get_data())["evidence_pending"]["source"] == "x"
    assert not any(isinstance(m, SendMessage) and m.chat_id == NAZ for m in bot.sent)
    await state.clear()


async def test_closed_day_writes_nothing(bot_dp, monkeypatch):
    main, bot = bot_dp
    _seed()
    from services import nazoratchi_day

    monkeypatch.setattr(nazoratchi_day, "check_active", lambda *a, **k: "closed")
    with pytest.raises(grading_webapp.WebAppError) as error:
        await grading_webapp.grade(bot, main.dp.storage, NAZ, CASHIER, "alo")
    assert error.value.status == 409 and _grades() == []


async def test_http_routes(bot_dp, monkeypatch):
    main, bot = bot_dp
    _seed()
    app = web.Application()
    webapp_server.add_routes(app, bot=bot, bot_token=_token(), fsm_storage=main.dp.storage)
    async with test_utils.TestClient(test_utils.TestServer(app)) as client:
        page = await client.get("/app/baholash")
        assert page.status == 200 and "telegram-web-app.js" in await page.text()
        assert page.headers["Cache-Control"] == "no-store" and "Access-Control-Allow-Origin" not in page.headers

        bad = await client.post("/api/baholash/day", json={"initData": "x"})
        assert bad.status == 401
        junk = await client.post("/api/baholash/day", data="not json")
        assert junk.status == 400

        monkeypatch.setattr(grading_webapp, "verify_init_data", lambda *a, **k: True)
        init = _signed(NAZ, _token())
        day = await client.post("/api/baholash/day", json={"initData": init})
        assert day.status == 200 and (await day.json())["work_date"] == "2026-11-03"
        graded = await client.post("/api/baholash/grade", json={"initData": init, "employee_id": CASHIER, "grade": "chala",
                                                                "eval_date": "2020-01-01"})
        body = await graded.json()
        assert graded.status == 200 and body["ok"]
        assert _grades() == [{"employee_id": CASHIER, "eval_date": "2026-11-03", "grade_key": "chala"}]  # sana — serverniki


def test_page_url_requires_https(monkeypatch):
    monkeypatch.delenv("WEBAPP_BASE_URL", raising=False)
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://fokus.example.com/")
    assert webapp_server.page_url() == "https://fokus.example.com/app/baholash"
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "http://insecure")
    assert webapp_server.page_url() is None
