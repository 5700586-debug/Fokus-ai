"""BOS (fiks oylik/bonus banki, nizomlar, kunlik baholash, jarima,
nazoratchi audit) uchun xom SQL qatlami. Biznes logika ``services/discipline.py``da.
"""

from datetime import datetime, timezone

from db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------- salaries --


def upsert_fixed_salary(user_id: int, fixed_salary: int, updated_by: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO salaries (user_id, fixed_salary, bonus_bank, updated_by, updated_at) "
            "VALUES (?, ?, 0, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "fixed_salary = excluded.fixed_salary, updated_by = excluded.updated_by, "
            "updated_at = excluded.updated_at",
            (user_id, fixed_salary, updated_by, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_salary(user_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM salaries WHERE user_id = ?", (user_id,)).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def _apply_bonus_delta(conn, user_id: int, delta: int, reason: str, ref_type: str, ref_id: int | None) -> int:
    """Berilgan ulanishda (COMMIT QILMASDAN) bonus balansiga ATOMIK delta qo'shadi va ledgerga audit
    yozuvi qo'shadi; yangi balansni qaytaradi. ``salaries`` qatori yo'q bo'lsa ``fixed_salary=0`` bilan
    yaratiladi. Delta bitta ``UPSERT`` bilan qo'shiladi (o'qib-keyin-yozish emas), shuning uchun parallel
    o'zgarishlar bir-birining yangilanishini yo'qotmaydi."""
    now = _now()
    conn.execute(
        "INSERT INTO salaries (user_id, fixed_salary, bonus_bank, updated_by, updated_at) "
        "VALUES (?, 0, ?, NULL, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "bonus_bank = salaries.bonus_bank + excluded.bonus_bank, updated_at = excluded.updated_at",
        (user_id, delta, now),
    )
    new_balance = conn.execute("SELECT bonus_bank FROM salaries WHERE user_id = ?", (user_id,)).fetchone()["bonus_bank"]
    conn.execute(
        "INSERT INTO bonus_bank_ledger "
        "(user_id, change_amount, balance_after, reason, ref_type, ref_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, delta, new_balance, reason, ref_type, ref_id, now),
    )
    return new_balance


def adjust_bonus_bank(
    user_id: int, delta: int, reason: str, ref_type: str, ref_id: int | None
) -> int:
    """``salaries`` qatori yo'q bo'lsa ``fixed_salary=0`` bilan yaratadi,
    yangi balansni yozadi va ``bonus_bank_ledger``ga audit yozuvi qo'shadi.
    Yangi balansni qaytaradi.
    """
    conn = get_connection()
    try:
        balance = _apply_bonus_delta(conn, user_id, delta, reason, ref_type, ref_id)
        conn.commit()
        return balance
    finally:
        conn.close()


def get_bonus_ledger_totals_since(user_id: int, since_iso: str) -> dict:
    """``bonus_bank_ledger``dagi ``since_iso``dan keyingi yozuvlarni
    bonus va minus qatorlarga ajratib yig'adi — joriy davr (masalan joriy
    oy) uchun alohida Bonus/Minus/Jami ko'rsatish (dashboard). Kunlik baho
    (``ref_type='daily_evaluation'``) yozuvlari SOF qo'shiladi: 3 -> 2
    tuzatishi (-1) intizomiy minus emas, bonusni 3 dan 2 ga tushiradi.
    Jarima, apellyatsiya qaytarishi va boshqa yozuvlar ishorasi bo'yicha
    ajratiladi. Balansning o'zi (``salaries.bonus_bank``) umrbod
    yig'iladigan qiymat bo'lib qoladi — bu funksiya faqat KO'RSATISH uchun
    davr bo'yicha filtrlangan yig'indi beradi, hech narsani qayta
    yozmaydi/tiklamaydi."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT "
            "COALESCE(SUM(CASE WHEN ref_type = 'daily_evaluation' THEN change_amount "
            "WHEN change_amount > 0 THEN change_amount ELSE 0 END), 0) AS bonus, "
            "COALESCE(SUM(CASE WHEN ref_type = 'daily_evaluation' THEN 0 "
            "WHEN change_amount < 0 THEN -change_amount ELSE 0 END), 0) AS minus "
            "FROM bonus_bank_ledger WHERE user_id = ? AND created_at >= ?",
            (user_id, since_iso),
        ).fetchone()
    finally:
        conn.close()

    bonus = row["bonus"] if row else 0
    minus = row["minus"] if row else 0
    return {"bonus": bonus, "minus": minus, "net": bonus - minus}


def get_bonus_ledger(user_id: int, limit: int = 20) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM bonus_bank_ledger WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


# --------------------------------------------------------- company rules --


def create_rule(rule_number: int, title: str, content: str, created_by: int) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO company_rules "
            "(rule_number, title, content, is_active, created_by, created_at) "
            "VALUES (?, ?, ?, 1, ?, ?)",
            (rule_number, title, content, created_by, _now()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_rule_by_number(rule_number: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM company_rules WHERE rule_number = ? AND is_active = 1",
            (rule_number,),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def list_active_rules() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM company_rules WHERE is_active = 1 ORDER BY rule_number"
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def list_rules_with_penalty_amount() -> list[dict]:
    """Faqat Founder ``default_penalty_amount`` belgilab qo'ygan
    ("tasdiqlangan") nizom bandlari — Nazoratchi tugma orqali ball
    ayirish uchun. Yangi nizom bandi standart holatda bu ro'yxatda
    KO'RINMAYDI, chunki miqdor ustuni ``NULL`` bo'lib boshlanadi
    (qarang ``db.py``dagi ``_ADDITIVE_COLUMNS``)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM company_rules WHERE is_active = 1 AND default_penalty_amount IS NOT NULL "
            "ORDER BY rule_number"
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def set_rule_penalty_amount(rule_number: int, amount: int) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE company_rules SET default_penalty_amount = ? WHERE rule_number = ? AND is_active = 1",
            (amount, rule_number),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


CATALOG_KINDS = ("nizom", "bonus_model", "culture", "checklist")
_CATALOG_META_FIELDS = ("catalog_kind", "source_key", "source_name")


def list_catalog_rules() -> list[dict]:
    """Import qilingan katalog bandlari (nizom, bonus modeli, madaniyat, chek-listlar) — rule_number tartibida."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM company_rules WHERE is_active = 1 AND catalog_kind IS NOT NULL ORDER BY rule_number"
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def list_learning_rules() -> list[dict]:
    """Nizom o'rganish oqimi uchun: eski (katalog metadatasiz) bandlar va rasmiy ``nizom``lar. Madaniyat, bonus modeli
    va lavozim chek-listlari xodimga majburan o'qitilmaydi."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM company_rules WHERE is_active = 1 AND (catalog_kind IS NULL OR catalog_kind = 'nizom') "
            "ORDER BY rule_number"
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def list_penalty_options(rule_number: int | None = None) -> list[dict]:
    conn = get_connection()
    try:
        if rule_number is None:
            rows = conn.execute(
                "SELECT * FROM company_rule_penalty_options WHERE is_active = 1 ORDER BY rule_number, id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM company_rule_penalty_options WHERE is_active = 1 AND rule_number = ? ORDER BY id",
                (rule_number,),
            ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_penalty_option(option_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM company_rule_penalty_options WHERE id = ? AND is_active = 1", (option_id,)
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


class _CatalogConflict(Exception):
    pass


def _rule_differences(existing: dict, row: dict) -> tuple[list[str], list[str]]:
    """(kontent farqlari, metadata farqlari). Metadata farqi faqat mavjud qiymat NULL bo'lsa 'to'ldirish' deb sanaladi."""
    content_diff = [
        field for field in ("title", "content", "default_penalty_amount")
        if existing.get(field) != row[field]
    ]
    meta_diff = [field for field in _CATALOG_META_FIELDS if existing.get(field) != row[field]]
    return content_diff, meta_diff


def import_catalog(rule_rows: list[dict], option_rows: list[dict], *, created_by: int, apply: bool) -> dict:
    """Katalogni BITTA tranzaksiyada import qiladi (``apply=False`` — faqat reja, hech narsa yozilmaydi). Reja ikkala
    rejimda ham bir xil kod bilan tuziladi. Mavjud bir xil key/raqamda BOSHQA matn/ball bo'lsa ustidan yozmaydi —
    konflikt qaytaradi va apply bekor qilinadi. Mavjud o'quv snapshotlari, tarix, baho va balansga tegilmaydi."""
    conn = get_connection()
    result = {
        "rules_inserted": 0, "rules_adopted": 0, "rules_unchanged": 0,
        "options_inserted": 0, "options_unchanged": 0, "conflicts": [],
    }
    try:
        rule_actions: list[tuple[str, dict]] = []
        for row in rule_rows:
            existing = conn.execute("SELECT * FROM company_rules WHERE rule_number = ?", (row["rule_number"],)).fetchone()
            by_key = conn.execute(
                "SELECT rule_number FROM company_rules WHERE source_key = ?", (row["source_key"],)
            ).fetchone()
            label = f"{row['source_key']} (rule_number={row['rule_number']})"
            if existing is None:
                if by_key is not None:
                    result["conflicts"].append(f"{label}: source_key boshqa rule_number'da ({by_key['rule_number']})")
                else:
                    rule_actions.append(("insert", row))
                continue

            existing = dict(existing)
            if not existing["is_active"]:
                result["conflicts"].append(f"{label}: mavjud band nofaol")
                continue
            content_diff, meta_diff = _rule_differences(existing, row)
            if content_diff:
                result["conflicts"].append(f"{label}: mavjud band boshqa ({', '.join(content_diff)})")
            elif not meta_diff:
                result["rules_unchanged"] += 1
            elif all(existing.get(field) is None for field in meta_diff) and (
                by_key is None or by_key["rule_number"] == row["rule_number"]
            ):
                rule_actions.append(("adopt", row))  # faqat bo'sh metadata to'ldiriladi, matn/ball o'zgarmaydi
            else:
                result["conflicts"].append(f"{label}: katalog metadatasi boshqa ({', '.join(meta_diff)})")

        option_actions: list[dict] = []
        known_rules = {row["rule_number"] for row in rule_rows}
        for option in option_rows:
            existing = conn.execute(
                "SELECT * FROM company_rule_penalty_options WHERE variant_key = ?", (option["variant_key"],)
            ).fetchone()
            if existing is None:
                if option["rule_number"] not in known_rules:
                    result["conflicts"].append(f"{option['variant_key']}: band katalogda yo'q")
                else:
                    option_actions.append(option)
                continue
            diff = [
                field for field in ("rule_number", "points", "condition_text", "gate_text", "target", "apply_allowed", "written_warning")
                if dict(existing).get(field) != option[field]
            ]
            if diff:
                result["conflicts"].append(f"{option['variant_key']}: mavjud variant boshqa ({', '.join(diff)})")
            else:
                result["options_unchanged"] += 1

        if result["conflicts"]:
            return result

        result["rules_inserted"] = sum(1 for kind, _ in rule_actions if kind == "insert")
        result["rules_adopted"] = sum(1 for kind, _ in rule_actions if kind == "adopt")
        result["options_inserted"] = len(option_actions)
        if not apply:
            return result

        now = _now()
        for kind, row in rule_actions:
            if kind == "insert":
                cursor = conn.execute(
                    "INSERT INTO company_rules (rule_number, title, content, is_active, created_by, created_at, "
                    "default_penalty_amount, catalog_kind, source_key, source_name) "
                    "VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?) ON CONFLICT(rule_number) DO NOTHING",
                    (
                        row["rule_number"], row["title"], row["content"], created_by, now,
                        row["default_penalty_amount"], row["catalog_kind"], row["source_key"], row["source_name"],
                    ),
                )
                if cursor.rowcount <= 0:  # parallel import oldinroq yozdi: aynan shu qator bo'lsagina davom
                    current = conn.execute("SELECT * FROM company_rules WHERE rule_number = ?", (row["rule_number"],)).fetchone()
                    content_diff, meta_diff = _rule_differences(dict(current), row)
                    if content_diff or meta_diff:
                        raise _CatalogConflict(f"{row['source_key']}: parallel import boshqa qiymat yozdi")
                    result["rules_inserted"] -= 1
                    result["rules_unchanged"] += 1
            else:
                conn.execute(
                    "UPDATE company_rules SET catalog_kind = ?, source_key = ?, source_name = ? "
                    "WHERE rule_number = ? AND catalog_kind IS NULL AND source_key IS NULL",
                    (row["catalog_kind"], row["source_key"], row["source_name"], row["rule_number"]),
                )
        for option in option_actions:
            cursor = conn.execute(
                "INSERT INTO company_rule_penalty_options (variant_key, rule_number, points, condition_text, gate_text, "
                "target, apply_allowed, written_warning, is_active, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?) ON CONFLICT(variant_key) DO NOTHING",
                (
                    option["variant_key"], option["rule_number"], option["points"], option["condition_text"],
                    option["gate_text"], option["target"], option["apply_allowed"], option["written_warning"], now,
                ),
            )
            if cursor.rowcount <= 0:
                current = conn.execute(
                    "SELECT * FROM company_rule_penalty_options WHERE variant_key = ?", (option["variant_key"],)
                ).fetchone()
                if any(dict(current).get(f) != option[f] for f in ("rule_number", "points", "condition_text", "gate_text", "target")):
                    raise _CatalogConflict(f"{option['variant_key']}: parallel import boshqa qiymat yozdi")
                result["options_inserted"] -= 1
                result["options_unchanged"] += 1

        conn.commit()
        return result
    except _CatalogConflict as error:
        result["conflicts"].append(str(error))
        result.update(rules_inserted=0, rules_adopted=0, options_inserted=0)
        rollback = getattr(conn, "rollback", None)
        if rollback is not None:
            rollback()
        return result
    except BaseException:
        rollback = getattr(conn, "rollback", None)
        if rollback is not None:
            rollback()
        raise
    finally:
        conn.close()


def create_unmatched_report(
    employee_id: int, reported_by: int, report_text: str, ai_note: str | None = None
) -> int:
    """Nazoratchi "📝 Boshqa holat" orqali yozgan, hech qanday tasdiqlangan
    nizom bandiga mos kelmagan (yoki AI hali ulanmagan/xato bergan)
    holat — ball ayirilmaydi, faqat Founder ko'rib chiqishi uchun
    audit sifatida saqlanadi (qarang ``services/discipline.py``)."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO discipline_unmatched_reports "
            "(employee_id, reported_by, report_text, ai_note, status, created_at) "
            "VALUES (?, ?, ?, ?, 'sent_to_founder', ?)",
            (employee_id, reported_by, report_text, ai_note, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


# --------------------------------------------------------- daily grading --


def get_daily_evaluation(employee_id: int, eval_date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM daily_evaluations WHERE employee_id = ? AND eval_date = ?",
            (employee_id, eval_date),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def upsert_daily_evaluation(
    employee_id: int, supervisor_id: int, eval_date: str, grade_key: str, grade_points: int
) -> None:
    now = _now()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO daily_evaluations "
            "(employee_id, supervisor_id, eval_date, grade_key, grade_points, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(employee_id, eval_date) DO UPDATE SET "
            "supervisor_id = excluded.supervisor_id, grade_key = excluded.grade_key, "
            "grade_points = excluded.grade_points, updated_at = excluded.updated_at",
            (employee_id, supervisor_id, eval_date, grade_key, grade_points, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def save_daily_grade(
    employee_id: int, supervisor_id: int, eval_date: str, grade_key: str, grade_points: int, ledger_reason: str
) -> dict:
    """Bitta baholash — BITTA tranzaksiya: ``daily_evaluations`` + ``daily_evaluation_history`` +
    ``salaries.bonus_bank`` + ``bonus_bank_ledger``. Hammasi muvaffaqiyatli bo'lsagina commit; istalgan
    yozuv xato bersa hammasi bekor qilinadi (ulanish yopilganda yozilmagan o'zgarishlar tashlanadi) va
    qayta urinish noldan to'liq ishlaydi. Qaytadi: ``{"changed", "previous", "balance"}``.

    Xuddi shu baho (kalit + ball) allaqachon saqlangan bo'lsa hech narsa yozilmaydi (``changed=False``).
    Aks holda baho faqat o'qilgan qiymatda bo'lsagina o'zgaradi (``UPDATE ... WHERE grade_key/ball``;
    yangi qator uchun ``INSERT ... ON CONFLICT DO NOTHING``), shuning uchun parallel bir xil bosishlardan
    faqat BITTASI g'olib bo'ladi — tarix, ball va xabar bir marta."""
    conn = get_connection()
    try:
        for _ in range(3):
            row = conn.execute(
                "SELECT * FROM daily_evaluations WHERE employee_id = ? AND eval_date = ?",
                (employee_id, eval_date),
            ).fetchone()
            now = _now()

            if row is None:
                previous = None
                claimed = conn.execute(
                    "INSERT INTO daily_evaluations "
                    "(employee_id, supervisor_id, eval_date, grade_key, grade_points, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(employee_id, eval_date) DO NOTHING",
                    (employee_id, supervisor_id, eval_date, grade_key, grade_points, now, now),
                )
            else:
                previous = dict(row)
                if previous["grade_key"] == grade_key and previous["grade_points"] == grade_points:
                    return {"changed": False, "previous": previous, "balance": None}
                claimed = conn.execute(
                    "UPDATE daily_evaluations SET supervisor_id = ?, grade_key = ?, grade_points = ?, "
                    "updated_at = ? WHERE employee_id = ? AND eval_date = ? AND grade_key = ? AND grade_points = ?",
                    (
                        supervisor_id, grade_key, grade_points, now, employee_id, eval_date,
                        previous["grade_key"], previous["grade_points"],
                    ),
                )

            if claimed.rowcount <= 0:
                continue  # boshqa so'rov oldinroq o'zgartirdi — qayta o'qiladi

            conn.execute(
                "INSERT INTO daily_evaluation_history "
                "(employee_id, supervisor_id, eval_date, grade_key, grade_points, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (employee_id, supervisor_id, eval_date, grade_key, grade_points, now),
            )

            delta = grade_points - (previous["grade_points"] if previous else 0)
            if delta:
                balance = _apply_bonus_delta(conn, employee_id, delta, ledger_reason, "daily_evaluation", None)
            else:
                salary = conn.execute("SELECT bonus_bank FROM salaries WHERE user_id = ?", (employee_id,)).fetchone()
                balance = salary["bonus_bank"] if salary else 0

            conn.commit()
            return {"changed": True, "previous": previous, "balance": balance}
    except BaseException:
        rollback = getattr(conn, "rollback", None)  # PgConnection.close() ham yozilmaganini bekor qiladi
        if rollback is not None:
            rollback()
        raise
    finally:
        conn.close()

    raise RuntimeError("daily_evaluations: parallel o'zgarishlar tufayli baho saqlanmadi")


def add_evaluation_history(
    employee_id: int, supervisor_id: int, eval_date: str, grade_key: str, grade_points: int
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO daily_evaluation_history "
            "(employee_id, supervisor_id, eval_date, grade_key, grade_points, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (employee_id, supervisor_id, eval_date, grade_key, grade_points, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_evaluation_history(employee_id: int, eval_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM daily_evaluation_history WHERE employee_id = ? AND eval_date = ? ORDER BY id",
            (employee_id, eval_date),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_evaluations_for_date(eval_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM daily_evaluations WHERE eval_date = ? "
            "ORDER BY grade_points DESC, employee_id ASC",
            (eval_date,),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_points_totals(start_date: str, end_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT employee_id, SUM(grade_points) AS total_points FROM daily_evaluations "
            "WHERE eval_date >= ? AND eval_date <= ? GROUP BY employee_id",
            (start_date, end_date),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_penalty_totals(start_date: str, end_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT employee_id, SUM(amount) AS total_penalty FROM discipline_penalties "
            "WHERE penalty_date >= ? AND penalty_date <= ? GROUP BY employee_id",
            (start_date, end_date),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


# ------------------------------------------------------------- penalties --


def create_penalty(
    employee_id: int,
    supervisor_id: int,
    penalty_date: str,
    amount: int,
    rule_number: int,
    comment: str | None,
    ai_note: str | None,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO discipline_penalties "
            "(employee_id, supervisor_id, penalty_date, amount, rule_number, comment, "
            "ai_note, appeal_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'none', ?)",
            (employee_id, supervisor_id, penalty_date, amount, rule_number, comment, ai_note, _now()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_active_penalties_for_date(employee_id: int, penalty_date: str) -> list[dict]:
    """Shu kundagi AMALDAGI minuslar: apellyatsiya qondirilgan (bekor qilingan) yozuv chiqarilgan."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM discipline_penalties WHERE employee_id = ? AND penalty_date = ? "
            "AND (appeal_decision IS NULL OR appeal_decision != 'approved') ORDER BY id",
            (employee_id, penalty_date),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_penalty(penalty_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM discipline_penalties WHERE id = ?", (penalty_id,)
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def list_penalties_by_status(employee_id: int, appeal_status: str, limit: int = 10) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM discipline_penalties WHERE employee_id = ? AND appeal_status = ? "
            "ORDER BY id DESC LIMIT ?",
            (employee_id, appeal_status, limit),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def set_penalty_appeal(penalty_id: int, reason: str, voice_file_id: str | None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE discipline_penalties SET appeal_status = 'pending', "
            "appeal_reason = ?, appeal_voice_file_id = ? WHERE id = ?",
            (reason, voice_file_id, penalty_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_penalty_appeal_brief(penalty_id: int, brief: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE discipline_penalties SET appeal_ai_brief = ? WHERE id = ?",
            (brief, penalty_id),
        )
        conn.commit()
    finally:
        conn.close()


def decide_penalty_appeal(penalty_id: int, decision: str, decided_by: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE discipline_penalties SET appeal_status = 'resolved', "
            "appeal_decision = ?, appeal_decided_by = ?, appeal_decided_at = ? WHERE id = ?",
            (decision, decided_by, _now(), penalty_id),
        )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------- day closures --


def try_close_day(supervisor_id: int, closure_date: str, evaluated_count: int, total_count: int) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO daily_closures "
            "(supervisor_id, closure_date, evaluated_count, total_count, closed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (supervisor_id, closure_date, evaluated_count, total_count, _now()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_closure(supervisor_id: int, closure_date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM daily_closures WHERE supervisor_id = ? AND closure_date = ?",
            (supervisor_id, closure_date),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


# -------------------------------------------------------- supervisor audit --


def try_record_supervisor_audit(
    supervisor_id: int, audit_date: str, event_type: str, penalty_amount: int
) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO supervisor_audit "
            "(supervisor_id, audit_date, event_type, penalty_amount, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (supervisor_id, audit_date, event_type, penalty_amount, _now()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------- branch review sessions --


def open_branch_session(supervisor_id: int, branch: str, session_date: str) -> dict:
    """Sessiya (nazoratchi + filial + sana) mavjud bo'lmasa ochadi; mavjudini qaytaradi."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO nazoratchi_branch_sessions "
            "(supervisor_id, branch, session_date, status, opened_at) VALUES (?, ?, ?, 'open', ?)",
            (supervisor_id, branch, session_date, _now()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM nazoratchi_branch_sessions WHERE supervisor_id = ? AND branch = ? AND session_date = ?",
            (supervisor_id, branch, session_date),
        ).fetchone()
    finally:
        conn.close()

    return dict(row)


def get_branch_session(supervisor_id: int, branch: str, session_date: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM nazoratchi_branch_sessions WHERE supervisor_id = ? AND branch = ? AND session_date = ?",
            (supervisor_id, branch, session_date),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def close_branch_session(session_id: int, evaluated_count: int, total_count: int) -> bool:
    """Atomik ``open -> closed``: takroriy/parallel yopish ``False`` qaytaradi."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE nazoratchi_branch_sessions SET status = 'closed', evaluated_count = ?, total_count = ?, "
            "closed_at = ? WHERE id = ? AND status = 'open'",
            (evaluated_count, total_count, _now(), session_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def list_open_branch_sessions(supervisor_id: int, before_date: str | None = None, on_date: str | None = None) -> list[dict]:
    clauses = ["supervisor_id = ?", "status = 'open'"]
    params: list = [supervisor_id]
    if before_date is not None:
        clauses.append("session_date < ?")
        params.append(before_date)
    if on_date is not None:
        clauses.append("session_date = ?")
        params.append(on_date)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM nazoratchi_branch_sessions WHERE " + " AND ".join(clauses) +
            " ORDER BY session_date, branch",
            tuple(params),
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]
