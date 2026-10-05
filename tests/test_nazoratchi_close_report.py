"""Filial nazorati yopilganda xodimlarning kunlik natijalari xabari (faqat o'qish + formatlash)."""

import pytest

import company_time
import employees
from config import FOUNDER_ID, RECRUITING_BRANCH_NAMES
from repositories import discipline as discipline_repo
from repositories import time_bonus as time_bonus_repo
from services import attendance as attendance_service
from services import discipline, nazoratchi_close_report as report, nazoratchi_day
from tests.bot_harness import send_callback

pytestmark = pytest.mark.anyio

BRANCH_A, BRANCH_B = RECRUITING_BRANCH_NAMES[0], RECRUITING_BRANCH_NAMES[1]
SUPERVISOR = 1


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _today() -> str:
    return company_time.today().isoformat()


def _ymd(iso: str | None = None) -> str:
    return (iso or _today()).replace("-", "")


def _employee(user_id: int, branch: str, surname: str) -> None:
    from roles import set_role

    set_role(user_id, "sotuvchi", set_by=FOUNDER_ID)
    employees.submit_profile(
        user_id, {"familiya": surname, "ism": "T", "branch": branch, "role_key": "sotuvchi", "contacts": []}
    )
    employees.approve_profile(user_id, approved_by=FOUNDER_ID)


def _supervisor() -> None:
    from roles import set_role

    set_role(SUPERVISOR, "nazoratchi", set_by=FOUNDER_ID)


def _grade(user_id: int, key: str, date: str | None = None) -> None:
    discipline.record_daily_grade(user_id, SUPERVISOR, date or _today(), key)


def _penalty(user_id: int, amount: int, comment: str | None, date: str | None = None) -> int:
    return discipline_repo.create_penalty(user_id, SUPERVISOR, date or _today(), amount, 1, comment, None)


@pytest.fixture
def rule(temp_db):
    discipline.add_rule(1, "Kechikish", "Ish vaqtiga kech qolish", FOUNDER_ID)


def _build(branch: str = BRANCH_A, date: str | None = None) -> list[str]:
    date = date or _today()
    statuses = nazoratchi_day.branch_statuses(branch, date, exclude_user_id=SUPERVISOR)
    evaluated = sum(1 for s in statuses if s.status == nazoratchi_day.STATUS_EVALUATED)
    return report.build_close_report(branch, date, statuses, evaluated, len(statuses))


def test_zero_grade_is_zero_and_unconfirmed_time_is_not_zero(rule):
    _employee(111, BRANCH_A, "Toshmat")
    _grade(111, discipline.GRADE_BAJARILMAGAN)  # haqiqiy 0 ball

    text = "\n".join(_build())
    assert "• Toshmat T — vaqt: tasdiqlanmagan, ish: 0, minus: 0" in text
    assert "baholangan: 1/1" in text
    assert "qo'yilmagan" not in text


def test_time_bonus_and_work_grade_shown_separately(rule):
    _employee(111, BRANCH_A, "Eshmat")
    _grade(111, discipline.GRADE_ALO)
    time_bonus_repo.grant(111, _today(), time_bonus_repo.SOURCE_MANUAL, SUPERVISOR)

    text = "\n".join(_build())
    assert "• Eshmat T — vaqt: ✅ berildi, ish: +3 ⭐, minus: 0" in text
    assert "💰" not in text and "so'm" not in text.lower()  # pul chiqmaydi


def test_missing_grade_is_not_turned_into_zero(rule):
    _employee(111, BRANCH_A, "Eshmat")
    _grade(111, discipline.GRADE_NORMA, date="2000-01-01")  # boshqa sana — bugun bahosi yo'q

    block = report._employee_block(
        nazoratchi_day.employee_status(employees.get_profile(111), _today()), _today()
    )
    assert "ish: qo'yilmagan" in block and "ish: 0" not in block


def test_minus_with_reason_is_separate_and_cancelled_minus_excluded(rule):
    _employee(111, BRANCH_A, "Surayyo")
    _grade(111, discipline.GRADE_NORMA)
    _penalty(111, 3, "Telefon")
    _penalty(111, 2, "Kech keldi")
    cancelled = _penalty(111, 30, "Bekor qilingan sabab")
    discipline_repo.decide_penalty_appeal(cancelled, discipline.DECISION_APPROVED, FOUNDER_ID)
    rejected = _penalty(111, 1, "Rad etilgan e'tiroz")
    discipline_repo.decide_penalty_appeal(rejected, discipline.DECISION_REJECTED, FOUNDER_ID)

    text = "\n".join(_build())
    assert "ish: +2 ⭐, minus: −6 ❌" in text  # 3+2+1; bekor qilingan 30 qo'shilmagan; net'ga qo'shilmagan
    assert "Sabab: Telefon; Kech keldi; Rad etilgan e'tiroz" in text
    assert "Bekor qilingan sabab" not in text


def test_reason_falls_back_to_rule_title(rule):
    _employee(111, BRANCH_A, "Surayyo")
    _grade(111, discipline.GRADE_CHALA)
    _penalty(111, 3, None)

    assert "Sabab: Kechikish" in "\n".join(_build())


def test_off_employee_listed_separately_not_as_row(rule):
    _employee(111, BRANCH_A, "Eshmat")
    _employee(113, BRANCH_A, "Ali")
    _employee(114, BRANCH_A, "Vali")
    _grade(111, discipline.GRADE_NORMA)
    attendance_service.set_scheduled_day_off(113, _today(), "test")
    attendance_service.set_scheduled_day_off(114, _today(), "test")

    text = "\n".join(_build())
    assert "Damda: Ali T, Vali T" in text
    assert "• Ali T" not in text and "• Vali T" not in text
    assert "baholangan: 1/3" in text  # mavjud hisob (total) o'zgarmagan


def test_other_date_and_other_branch_records_do_not_mix(rule):
    _employee(111, BRANCH_A, "Eshmat")
    _employee(222, BRANCH_B, "Botir")
    _grade(111, discipline.GRADE_NORMA)
    _grade(222, discipline.GRADE_ALO)
    _penalty(111, 9, "Kecha jarima", date="2000-01-01")
    _penalty(222, 5, "Boshqa filial")
    time_bonus_repo.grant(111, "2000-01-01", time_bonus_repo.SOURCE_MANUAL, SUPERVISOR)

    text = "\n".join(_build())
    assert "Botir" not in text and "Boshqa filial" not in text and "Kecha jarima" not in text
    assert "• Eshmat T — vaqt: tasdiqlanmagan, ish: +2 ⭐, minus: 0" in text


def test_long_report_is_split_without_breaking_employee_rows(rule, monkeypatch):
    for index in range(30):
        _employee(1000 + index, BRANCH_A, f"Xodim{index:02d}")
        _grade(1000 + index, discipline.GRADE_NORMA)
        _penalty(1000 + index, 3, f"Sabab{index:02d}")
    monkeypatch.setattr(report, "MAX_MESSAGE_CHARS", 600)

    chunks = _build()
    assert len(chunks) > 1
    assert all(len(chunk) <= 600 for chunk in chunks)
    assert "nazorati yopildi" in chunks[0] and all("nazorati yopildi" not in c for c in chunks[1:])
    for index in range(30):
        name = f"Xodim{index:02d} T"
        home = [c for c in chunks if f"• {name} —" in c]
        assert len(home) == 1 and f"Sabab{index:02d}" in home[0]  # qator va sababi birga


async def test_bot_sends_report_only_after_successful_close(bot_dp, rule):
    main, bot = bot_dp
    _supervisor()
    _employee(111, BRANCH_A, "Pending")
    _employee(113, BRANCH_A, "Nograf")
    attendance_service.set_scheduled_work_shift(111, _today(), "09:00", "18:00", "test")
    _grade(113, discipline.GRADE_ALO)

    blocked = await send_callback(main.dp, bot, SUPERVISOR, data=f"bos:close:0:{_ymd()}", target_chat_id=SUPERVISOR)
    assert "Yopib bo'lmaydi" in blocked[0].text
    assert not any("nazorati yopildi" in (getattr(m, "text", "") or "") for m in blocked)

    _grade(111, discipline.GRADE_NORMA)
    closed = await send_callback(main.dp, bot, SUPERVISOR, data=f"bos:close:0:{_ymd()}", target_chat_id=SUPERVISOR)
    text = closed[0].text
    assert f"✅ {BRANCH_A} nazorati yopildi" in text and "baholangan: 2/2" in text
    assert "• Pending T" in text and "• Nograf T" in text

    again = await send_callback(main.dp, bot, SUPERVISOR, data=f"bos:close:0:{_ymd()}", target_chat_id=SUPERVISOR)
    assert "allaqachon yopilgan" in again[0].text and "• " not in again[0].text
