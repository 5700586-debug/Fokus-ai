"""🗓 Grafik ekrani: filial rahbari — faqat o'z filiali va boshlanmagan smenalar; nazoratchi — sabab bilan;
yulduz qarori chiqqan oy qulflangan; bitta xato — hech narsa yozilmaydi; grafik o'zgarsa vaqt bonusi qayta hisoblanadi."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from aiogram.methods import SendMessage
from aiohttp import test_utils, web

import company_time
import webapp_server
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from db import get_connection
from services import grading_webapp, permissions
from services import schedule_webapp as sw
from services import work_time

pytestmark = pytest.mark.anyio

NAZ, BOSS, EMP, FAR, CASHIER_ONLY = 1, 801, 802, 803, 804
B0, B1 = RECRUITING_BRANCH_NAMES[0], RECRUITING_BRANCH_NAMES[1]
FIXED = datetime(2026, 11, 3, 12, 0, tzinfo=ZoneInfo("Asia/Tashkent"))  # seshanba 12:00


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(company_time, "now", lambda: FIXED)
    grading_webapp._hits.clear()


def _sql(sql, params=()):
    conn = get_connection()
    try:
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()] if sql.lstrip().upper().startswith("SELECT") else None
        conn.commit()
        return rows
    finally:
        conn.close()


def _seed():
    from roles import set_role

    set_role(NAZ, "nazoratchi", set_by=FOUNDER_ID)
    set_role(BOSS, "savdo_boshligi", set_by=FOUNDER_ID)
    set_role(CASHIER_ONLY, "kassir", set_by=FOUNDER_ID)
    for uid, fam, branch in ((BOSS, "Rahbar", B0), (EMP, "Kassir", B0), (FAR, "Uzoq", B1), (CASHIER_ONLY, "Boshqa", B0)):
        _sql("INSERT INTO employees (user_id, familiya, ism, branch, status) VALUES (?, ?, 'X', ?, 'approved')",
             (uid, fam, branch))


def _shift(emp, day, start="08:00", end="18:00"):
    _sql("INSERT INTO employee_scheduled_shifts (employee_id, shift_date, planned_start, planned_end, status, source, "
         "created_at) VALUES (?, ?, ?, ?, 'work', 'test', 'x')", (emp, day, start, end))


def _change(emp, day, status="work", start="08:00", end="18:00", version=0):
    return {"employee_id": emp, "date": day, "status": status, "start": start, "end": end, "expected_version": version}


def _status(fn) -> int:
    with pytest.raises(grading_webapp.WebAppError) as error:
        fn()
    return error.value.status


def _shift_row(emp, day):
    rows = _sql("SELECT status, planned_start, planned_end FROM employee_scheduled_shifts WHERE employee_id = ? "
                "AND shift_date = ?", (emp, day))
    return rows[0] if rows else None


def test_permissions_are_separate_from_old_schedule_commands():
    _seed()
    assert sw.can_open(BOSS) and not sw.is_full(BOSS)
    assert not permissions.has_permission(BOSS, permissions.ACTION_MANAGE_DAILY_SCHEDULE)  # eski buyruqlar yopiq
    assert sw.can_open(NAZ) and sw.is_full(NAZ)
    assert not sw.can_open(CASHIER_ONLY)


def test_week_payload_branch_limits_and_locks():
    _seed()
    boss = sw.week_payload(BOSS)
    assert boss["week_start"] == "2026-11-02" and [d["date"] for d in boss["days"]][-1] == "2026-11-08"
    assert [b["name"] for b in boss["branches"]] == [B0]
    ids = {e["id"] for e in boss["branches"][0]["employees"]}
    assert EMP in ids and BOSS not in ids and FAR not in ids
    cells = {c["date"]: c for c in next(e for e in boss["branches"][0]["employees"] if e["id"] == EMP)["cells"]}
    assert cells["2026-11-02"]["locked"] == sw.LOCK_STARTED and cells["2026-11-05"]["locked"] is None
    naz = sw.week_payload(NAZ)
    naz_cells = {c["date"]: c for b in naz["branches"] for e in b["employees"] if e["id"] == EMP for c in e["cells"]}
    assert naz_cells["2026-11-02"]["locked"] is None and naz_cells["2026-11-02"]["late"]
    assert "+998" not in str(naz)
    assert _status(lambda: sw.week_payload(NAZ, "2027-06-01")) == 400  # juda uzoq hafta


def test_boss_edits_future_shift_with_history_and_notice():
    _seed()
    result = sw.save(BOSS, [_change(EMP, "2026-11-05"), _change(EMP, "2026-11-06", "off", None, None)], None)
    assert result["saved"] == 2 and [d for d, _t in result["notify"][EMP]] == ["2026-11-05", "2026-11-06"]
    assert "Grafigingiz o'zgardi" in sw.notify_text(result["notify"][EMP]) and "dam" in sw.notify_text(result["notify"][EMP])
    assert _shift_row(EMP, "2026-11-05") == {"status": "work", "planned_start": "08:00", "planned_end": "18:00"}
    rev = _sql("SELECT changed_by, is_late_change FROM employee_schedule_revisions WHERE employee_id = ? "
               "AND shift_date = '2026-11-05'", (EMP,))
    assert rev == [{"changed_by": BOSS, "is_late_change": 0}]
    history = sw.history(BOSS, EMP, "2026-11-05")["items"]
    assert history[0]["old"] == "—" and history[0]["new"] == "08:00–18:00" and history[0]["by"] == "Rahbar X"


def test_boss_cannot_touch_started_past_other_branch_self_or_entry_days():
    _seed()
    _shift(EMP, "2026-11-03")  # bugun 08:00 da boshlangan
    assert _status(lambda: sw.save(BOSS, [_change(EMP, "2026-11-03", "off", None, None, 0)], "x")) == 403
    assert _status(lambda: sw.save(BOSS, [_change(EMP, "2026-11-02")], "x")) == 403          # o'tgan kun
    assert _status(lambda: sw.save(BOSS, [_change(FAR, "2026-11-05")], None)) == 403         # boshqa filial
    assert _status(lambda: sw.save(BOSS, [_change(BOSS, "2026-11-05")], None)) == 403        # o'zini
    work_time.save_entry(EMP, "2026-11-07", "07:50", None, entered_by=NAZ)                  # kelish yozilgan kun
    assert _status(lambda: sw.save(BOSS, [_change(EMP, "2026-11-07", "off", None, None)], None)) == 403
    assert _shift_row(EMP, "2026-11-03")["status"] == "work" and _shift_row(EMP, "2026-11-02") is None


def test_today_not_started_is_editable_but_new_start_in_past_is_not():
    _seed()
    _shift(FAR, "2026-11-03", "14:00", "22:00")
    from roles import set_role

    set_role(BOSS + 100, "savdo_boshligi", set_by=FOUNDER_ID)
    _sql("INSERT INTO employees (user_id, familiya, ism, branch, status) VALUES (?, 'Rahbar2', 'X', ?, 'approved')",
         (BOSS + 100, B1))
    assert sw.save(BOSS + 100, [_change(FAR, "2026-11-03", start="15:00", end="22:00")], None)["saved"] == 1
    version = sw.week_payload(BOSS + 100)["branches"][0]["employees"][0]["cells"][1]["version"]
    assert _status(lambda: sw.save(BOSS + 100, [_change(FAR, "2026-11-03", start="10:00", end="22:00",
                                                         version=version)], None)) == 403


def test_nazoratchi_late_change_needs_reason_and_resyncs_bonus():
    _seed()
    _shift(EMP, "2026-11-02")
    work_time.save_entry(EMP, "2026-11-02", "07:50", "18:00", entered_by=NAZ)
    assert _sql("SELECT source FROM time_bonus_grants WHERE employee_id = ?", (EMP,)) == [{"source": "time_entry"}]
    assert _status(lambda: sw.save(NAZ, [_change(EMP, "2026-11-02", start="07:30")], None)) == 400
    assert sw.save(NAZ, [_change(EMP, "2026-11-02", start="07:30")], "grafik xato kiritilgan")["notify"] == {}
    assert _sql("SELECT * FROM time_bonus_grants WHERE employee_id = ?", (EMP,)) == []  # 07:50 > 07:30 — bonus yo'q
    rev = _sql("SELECT reason, is_late_change FROM employee_schedule_revisions WHERE employee_id = ? ORDER BY id DESC",
               (EMP,))[0]
    assert rev == {"reason": "grafik xato kiritilgan", "is_late_change": 1}


def test_any_error_writes_nothing_from_the_batch():
    _seed()
    first = sw.save(NAZ, [_change(EMP, "2026-11-05")], None)
    assert first["saved"] == 1
    stale = [_change(EMP, "2026-11-04"), _change(EMP, "2026-11-05", start="09:00", version=0)]  # 2-katak eskirgan
    assert _status(lambda: sw.save(NAZ, stale, None)) == 409
    assert _shift_row(EMP, "2026-11-04") is None and _shift_row(EMP, "2026-11-05")["planned_start"] == "08:00"
    assert _status(lambda: sw.save(NAZ, [_change(EMP, "2026-11-04"), _change(EMP, "2026-11-04")], None)) == 400
    assert _status(lambda: sw.save(NAZ, [_change(EMP, "2026-11-04", start="08:00", end="08:00")], None)) == 400
    assert _status(lambda: sw.save(NAZ, [], None)) == 400


def test_star_decision_month_is_locked_for_everyone():
    _seed()
    _sql("INSERT INTO star_history (user_id, year_month, previous_stars, new_stars, change, reason, created_at) "
         "VALUES (?, '2026-11', 0, 1, 1, 'test', 'x')", (EMP,))
    assert _status(lambda: sw.save(NAZ, [_change(EMP, "2026-11-05")], "sabab")) == 409
    cells = sw.week_payload(BOSS)["branches"][0]["employees"]
    assert all(c["locked"] == sw.LOCK_STAR for e in cells if e["id"] == EMP for c in e["cells"])


async def test_routes_save_and_notify(bot_dp, monkeypatch):
    main, bot = bot_dp
    _seed()
    app = web.Application()
    webapp_server.add_routes(app, bot=bot, bot_token=os.environ["BOT_TOKEN"], fsm_storage=main.dp.storage)
    monkeypatch.setattr(grading_webapp, "verify_init_data", lambda *a, **k: True)
    init = "user=%7B%22id%22%3A" + str(BOSS) + "%7D&auth_date=1&hash=x"
    async with test_utils.TestClient(test_utils.TestServer(app)) as client:
        page = await client.get("/app/grafik")
        assert page.status == 200 and "telegram-web-app.js" in await page.text()
        week = await client.post("/api/grafik/week", json={"initData": init})
        assert week.status == 200 and (await week.json())["week_start"] == "2026-11-02"
        bot.sent.clear()
        saved = await client.post("/api/grafik/save", json={"initData": init, "changes": [_change(EMP, "2026-11-05")]})
        body = await saved.json()
        assert saved.status == 200 and body["saved"] == 1 and body["notified"] == 1 and "notify" not in body
        assert any(isinstance(m, SendMessage) and m.chat_id == EMP and "Grafigingiz" in m.text for m in bot.sent)
        denied = await client.post("/api/grafik/week", json={"initData": init.replace(str(BOSS), str(CASHIER_ONLY))})
        assert denied.status == 403
