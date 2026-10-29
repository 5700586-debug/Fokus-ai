"""/mystars: barcha o'qishlar BITTA ulanishda, takroriy o'qishlarsiz; natija eski (har o'qish alohida ulanishda)
yo'ldagi bilan aynan bir xil. Eski yo'l shu faylda mos yozuv sifatida saqlangan (public per-day funksiyalar)."""

import asyncio
from datetime import date, timedelta

import pytest

import company_time
import db
import employees
from config import FOUNDER_ID
from roles import set_role
from services import attendance as svc
from services import discipline, employee_dashboard, latency_probe, star_engine
from tests.bot_harness import send
from tests.test_month_hours_queries import _counted, _employee, _legacy_month, _seed, _today

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _base_mystars(user: int):
    """PR #58 ning HAQIQIY baseline'i (main 555fef4, PR #57 dan keyin): har o'qish alohida ulanishda; profil kontaktlari bilan
    o'qiladi; oxirgi 2 kun har kun uchun alohida voqealar+sabab so'rovi; oylik soat diapazon bo'yicha (PR #57); 'kecha'
    'oxirgi 2 kun'dan olinadi. Mustaqil o'lchovda (555fef4 worktree) 31 kunlik ma'lumotda oldin 12, hozir 11 execute / 10 pool (eski yo'l ham optimallashtirilgan)."""
    profile = employees.get_profile(user)
    recent = [svc.get_day_summary(user, (company_time.today() - timedelta(days=i)).isoformat()) for i in range(2)]
    yesterday_iso = (company_time.today() - timedelta(days=1)).isoformat()
    yesterday = next(day for day in recent if day["date"] == yesterday_iso)
    return (
        star_engine.get_current_stars(user),
        star_engine.get_bonus_history(user),
        {
            "full_name": " ".join(p for p in (profile.get("familiya"), profile.get("ism")) if p) or "-",
            "points": discipline.get_period_point_totals(user),
            "yesterday": yesterday,
            "hours": svc.get_month_to_date_hours(user, profile=profile),
            "recent_days": recent,
        },
    )


def _legacy_mystars(user: int):
    """TARIXIY (PR #57 dan OLDINGI) yo'l: har o'qish alohida ulanishda, kunlar bo'yicha o'qish. PR #58 ning baseline'i EMAS —
    faqat tarixiy regressiya (kunlar soniga chiziqli o'sish) uchun."""
    profile = employees.get_profile(user)
    return (
        star_engine.get_current_stars(user),
        star_engine.get_bonus_history(user),
        {
            "full_name": " ".join(p for p in (profile.get("familiya"), profile.get("ism")) if p) or "-",
            "points": discipline.get_period_point_totals(user),
            "yesterday": svc.get_yesterday_summary(user),
            "hours": _legacy_month(user),
            "recent_days": [
                svc.get_day_summary(user, (company_time.today() - timedelta(days=i)).isoformat()) for i in range(2)
            ],
        },
    )


@pytest.mark.parametrize("today", ["2026-03-01", "2026-03-31", "2026-04-02", "2027-01-02"])
def test_single_connection_path_returns_exactly_the_real_base_result_with_fewer_round_trips(monkeypatch, today):
    _today(monkeypatch, today)
    user = _employee()
    _seed(user, date.fromisoformat(today) - timedelta(days=35), date.fromisoformat(today) + timedelta(days=2))

    (stars_n, history_n, dash), q_new, p_new = _counted(lambda: employee_dashboard.read_mystars(user))
    (stars_b, history_b, base), q_base, p_base = _counted(lambda: _base_mystars(user))

    assert (stars_n, history_n) == (stars_b, history_b)
    assert dash["profile"]["full_name"] == base["full_name"] and dash["points"] == base["points"]
    assert dash["hours"] == base["hours"] and dash["yesterday"] == base["yesterday"] and dash["recent_days"] == base["recent_days"]
    print(f"{today}: yangi sql={q_new} pool={p_new}; haqiqiy base (555fef4) sql={q_base} pool={p_base}")
    assert (q_base, p_base) == (11, 10) and (q_new, p_new) == (9, 1)  # kunlar soniga bog'liq emas


@pytest.mark.parametrize("today", ["2026-03-01", "2026-03-31", "2026-04-02", "2027-01-02"])
def test_new_single_connection_path_returns_exactly_the_pre_pr57_historical_result(monkeypatch, today):
    _today(monkeypatch, today)
    user = _employee()
    _seed(user, date.fromisoformat(today) - timedelta(days=35), date.fromisoformat(today) + timedelta(days=2))

    (stars_n, history_n, dash), q_new, p_new = _counted(lambda: employee_dashboard.read_mystars(user))
    (stars_o, history_o, old), q_old, p_old = _counted(lambda: _legacy_mystars(user))

    assert (stars_n, history_n) == (stars_o, history_o)
    assert dash["profile"]["full_name"] == old["full_name"]
    assert dash["points"] == old["points"] and dash["hours"] == old["hours"]
    assert dash["yesterday"] == old["yesterday"] and dash["recent_days"] == old["recent_days"]
    print(f"{today}: yangi sql={q_new} pool={p_new}; eski sql={q_old} pool={p_old}")
    assert p_new == 1 and q_new < q_old and p_new < p_old


def test_unknown_grafik_and_missing_checkout_are_preserved_in_recent_days(monkeypatch):
    _today(monkeypatch, "2026-03-10")
    user = _employee()
    # kecha: faqat kelish (chiqish yo'q), grafik yo'q; bugun: voqea ham, sabab ham yo'q
    from repositories import attendance as repo

    repo.record_event(user, svc.EVENT_CHECK_IN, "2026-03-09T09:00:00+05:00", "test")
    repo.set_reason(user, "2026-03-09", svc.REASON_OTHER, "izoh")

    _, _, dash = employee_dashboard.read_mystars(user)

    yesterday, today = dash["yesterday"], dash["recent_days"][0]
    assert dash["recent_days"][1] == yesterday and yesterday["arrival_time"] == "09:00" and yesterday["note"] == "izoh"
    assert today["arrival_time"] is None and today["label"] == "Ma'lumot yo'q"
    assert dash["hours"]["planned_hours"] is None and dash["hours"]["missing_days_count"] == 10  # noma'lum, dam emas


class _Tracker:
    """SQLite ulanishlarini kuzatadi: nechta ochilgan va yopilgan."""

    def __init__(self, monkeypatch):
        self.opened, self.closed = [], []
        cls = db._MeasuredSqliteConnection
        original_init, original_close = cls.__init__, cls.close

        def init(inner, *args, **kwargs):
            original_init(inner, *args, **kwargs)
            self.opened.append(id(inner))

        def close(inner):
            self.closed.append(id(inner))
            return original_close(inner)

        monkeypatch.setattr(cls, "__init__", init)
        monkeypatch.setattr(cls, "close", close)

    @property
    def leaked(self) -> int:
        return len(set(self.opened) - set(self.closed))


def test_only_the_owner_closes_the_connection(monkeypatch):
    _today(monkeypatch, "2026-03-05")
    user = _employee()
    tracker = _Tracker(monkeypatch)

    conn = db.get_connection()
    employee_dashboard.build_dashboard(user, conn=conn)  # uzatilgan ulanish: ichki funksiyalar yopmaydi
    conn.execute("SELECT 1")  # hamon ochiq
    assert tracker.closed == []
    conn.close()
    assert tracker.leaked == 0

    employee_dashboard.build_dashboard(user)  # egasi o'zi ochadi va yopadi
    assert tracker.leaked == 0


def test_connection_does_not_leak_when_a_read_fails(monkeypatch):
    _today(monkeypatch, "2026-03-05")
    user = _employee()
    tracker = _Tracker(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("o'qish xatosi")

    monkeypatch.setattr(discipline, "get_period_point_totals", boom)

    with pytest.raises(RuntimeError, match="o'qish xatosi"):
        employee_dashboard.read_mystars(user)

    assert tracker.opened and tracker.leaked == 0


async def test_concurrent_reads_do_not_mix_users(monkeypatch):
    _today(monkeypatch, "2026-03-20")
    users = [_employee() for _ in range(3)]
    for index, user in enumerate(users):
        _seed(user, date(2026, 3, 1), date(2026, 3, 22))
        employees.submit_profile(user, {**employees.get_profile(user), "ism": f"Ism{index}", "contacts": []})

    results = await asyncio.gather(*(asyncio.to_thread(employee_dashboard.read_mystars, user) for user in users))

    assert [dash["profile"]["full_name"] for _, _, dash in results] == [f"T Ism{index}" for index in range(3)]


async def test_handler_closes_the_connection_before_replying_and_denies_unauthorized(bot_dp, monkeypatch):
    from aiogram.types import Message

    main, bot = bot_dp
    _today(monkeypatch, "2026-03-20")
    user = _employee()
    set_role(user, "kassir", set_by=FOUNDER_ID)
    tracker = _Tracker(monkeypatch)
    open_at_reply = []
    original = Message.answer

    async def answer(self, *args, **kwargs):
        open_at_reply.append(tracker.leaked)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(Message, "answer", answer)

    sent = await send(main.dp, bot, user, text="/mystars")

    assert sent and open_at_reply and set(open_at_reply) == {0}  # javob kutilganda ochiq ulanish yo'q
    assert tracker.opened  # o'qishlar bo'lgan

    def must_not_run(*args, **kwargs):
        raise AssertionError("ruxsatsiz foydalanuvchi uchun dashboard o'qilmasligi kerak")

    monkeypatch.setattr(employee_dashboard, "read_mystars", must_not_run)
    stranger = await send(main.dp, bot, 999991, text="/mystars")  # ruxsatsiz: rad etiladi, DB o'qilmaydi
    assert all("Joriy yulduzlar" not in (getattr(m, "text", "") or "") for m in stranger)
