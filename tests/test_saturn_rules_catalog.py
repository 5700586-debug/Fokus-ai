"""Saturn nizom/madaniyat/chek-list katalogi: asl manba yaxlitligi, manifest, import (dry-run/apply/idempotent/rollback),
ball variantlari va ``apply_penalty`` himoyasi. Telegram/OpenAI/production DB ishlatilmaydi."""

import hashlib
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from db import get_connection
from repositories import discipline as discipline_repo
from services import company_rules_import as importer
from services import discipline

SOURCE_SHA256 = "e836d6af6daeb3fdec42a6bf62755daff9e00af79e85e51a1881b83387766c10"
FOUNDER = 1


@pytest.fixture(scope="module")
def text() -> str:
    return importer.read_source()


@pytest.fixture(scope="module")
def manifest() -> dict:
    return importer.load_manifest()


@pytest.fixture(scope="module")
def src(text) -> importer.Source:
    return importer.Source(text)


def _count(table: str, where: str = "1=1") -> int:
    conn = get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}").fetchone()["n"]
    finally:
        conn.close()


# ------------------------------------------------------------ asl manba yaxlitligi --


def test_source_is_the_single_original_file_byte_for_byte(text, manifest):
    raw = importer.SOURCE_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA256 == manifest["source"]["sha256"]
    assert len(raw) == manifest["source"]["bytes"] == 63767
    assert manifest["source"]["original_name"] == "SATURN_NIZOM_CHEKLIST_MANBA.txt"
    assert b"\r" not in raw  # hech qanday "tozalash"/qator oxiri o'zgarishi yo'q
    assert importer.validate() == []


def test_manifest_is_reproducible_from_the_source_and_has_no_hand_typed_text(manifest):
    assert importer.build_manifest() == manifest
    assert "content" not in manifest["items"][0]  # matn manifestda emas — oraliqlar; import paytida manbadan kesiladi


def test_first_two_metadata_lines_and_separators_are_not_catalog_items(src, manifest):
    assert manifest["source"]["metadata_lines"] == [1, 2]
    assert src.lines[0].startswith("SATURN — KORPORATIV MADANIYAT") and src.lines[1].startswith("Matn o‘zgartirilmagan")
    item_lines = {n for item in manifest["items"] for n in range(item["title_line"], item["last_line"] + 1)}
    assert not item_lines & {1, 2}
    separators = [s["separator_line"] for s in manifest["sections"]]
    assert not item_lines & set(separators)
    assert all(src.lines[n - 1].startswith("##########") for n in separators)
    rows, options = importer.build_rows()
    assert not any("##########" in row["content"] or "##########" in row["title"] for row in rows)
    assert not any("Telegram vaqt belgilari" in row["content"] for row in rows)


def test_ten_sections_in_order_and_every_meaningful_line_is_covered(src, manifest):
    assert [s["name"] for s in manifest["sections"]] == list(importer.EXPECTED_SECTION_ORDER) and len(manifest["sections"]) == 10
    covered = set()
    for item in manifest["items"]:
        covered.update(range(item["title_line"], item["last_line"] + 1))
    for header in manifest["section_headers"]:
        covered.update(header["lines"])
    skipped = {1, 2} | {s["separator_line"] for s in manifest["sections"]}
    lost = [n for n, line in enumerate(src.lines, 1) if line.strip() and n not in covered and n not in skipped]
    assert lost == []  # birorta mazmunli manba bo'lagi jim yo'qolmagan


def test_bonus_model_is_not_rule_one_and_exactly_26_official_rules_follow_in_order(manifest):
    nizom_items = [i for i in manifest["items"] if i["section"] == "nizomlar"]
    assert nizom_items[0]["kind"] == "bonus_model" and nizom_items[0]["official_number"] is None
    assert nizom_items[0]["title"] == "BONUS VA MINUS BALLARNI HISOBLASH MODELI"
    rules = [i for i in nizom_items if i["kind"] == "nizom"]
    assert [i["official_number"] for i in rules] == list(range(1, 27)) == [i["rule_number"] for i in rules]
    for item, official in zip(rules, importer.OFFICIAL_NIZOM_TITLES):
        assert importer.normalize_title(item["title"]) == importer.normalize_title(official)
    assert rules[25]["title"] == "ISH JOYIDA ODOB VA PROFESSIONAL MASOFA" and rules[25]["rule_number"] == 26


def test_result_lines_examples_and_inner_lists_are_not_new_rules(manifest):
    titles = [i["title"] for i in manifest["items"]]
    assert not any(t.startswith("NATIJA") or t.startswith("Namuna") or t.startswith("Misol") for t in titles)
    assert len([i for i in manifest["items"] if i["kind"] == "nizom"]) == 26


def test_technical_ids_never_collide_with_official_numbers(manifest):
    technical = [i for i in manifest["items"] if i["kind"] != "nizom"]
    assert all(i["rule_number"] > 26 and i["official_number"] is None for i in technical)
    assert len({i["rule_number"] for i in manifest["items"]}) == len(manifest["items"])


def test_official_numbers_are_not_written_into_original_title_or_content(src):
    rows, _ = importer.build_rows()
    for row in rows:
        assert not re.match(r"^\s*\d+[.)-]", row["title"])
        assert row["content"] in src.text and row["title"] in src.text  # aynan manbadagi bo'laklar


def test_every_stored_text_is_an_exact_source_slice(src, manifest):
    rows, options = importer.build_rows()
    by_number = {row["rule_number"]: row for row in rows}
    for item in manifest["items"]:
        assert src.text[item["start"]:item["end"]] == src.slice(item["first_line"], item["last_line"])
        assert by_number[item["rule_number"]]["content"] in src.text
    for option in options:
        assert option["condition_text"] in src.text
        if option["gate_text"]:
            assert option["gate_text"] in src.text


def test_wrong_heading_count_or_order_stops_the_import(text):
    lines = text.split("\n")
    first = next(i for i, l in enumerate(lines) if l == "QOIDALAR ASOSIDA ISH TUTISH")
    removed = lines[:first] + ["Eslatma qatori"] + lines[first + 1:]
    with pytest.raises(importer.SourceError):
        importer.build_manifest("\n".join(removed))

    second = next(i for i, l in enumerate(lines) if l == "QOIDALAR HAMMA UCHUN BIR XIL")
    swapped = list(lines)
    swapped[first], swapped[second] = swapped[second], swapped[first]
    with pytest.raises(importer.SourceError):
        importer.build_manifest("\n".join(swapped))
    assert importer.validate("\n".join(swapped)) != []


def test_typographic_apostrophe_differences_are_tolerated_only_in_comparison():
    assert importer.normalize_title("XATOSINI O'ZI TAN OLISH") == importer.normalize_title("XATOSINI O‘ZI TAN OLISH ")
    assert importer.normalize_title("XATOSINI O'ZI TAN OLISH") != importer.normalize_title("XATOSINI O'ZI TAN OLMASH")


# ---------------------------------------------------------------- ball variantlari --


def test_every_option_points_come_from_the_exact_source_line(src, manifest):
    pattern = re.compile(r"[–−-]\s?(\d+)\s*ball", re.IGNORECASE)
    assert len(manifest["penalty_options"]) == 88
    for option in manifest["penalty_options"]:
        line = src.lines[option["line"] - 1]
        assert int(pattern.search(line).group(1)) == option["points"]
        assert src.text[option["points_start"]:option["points_end"]].lower().endswith("ball")


def test_money_percent_time_temperature_are_never_penalty_points(src, manifest):
    option_lines = {o["line"] for o in manifest["penalty_options"]}
    for needle in ("5 000", "300 000", "50 foiz", "+2°C", "40 daqiqa", "200 000"):
        for number, line in enumerate(src.lines, 1):
            if needle in line and number in option_lines:
                assert _PENALTY_ON_LINE.search(line), f"{needle!r} qatori faqat '–N ball' bo'lsa variant bo'ladi"
    assert {57, 59, 67} & option_lines == set()  # bonus modelidagi hisoblash MISOLLARI jarima emas
    bonus_model = next(i for i in manifest["items"] if i["kind"] == "bonus_model")
    assert not [o for o in manifest["penalty_options"] if o["item"] == bonus_model["key"]]


_PENALTY_ON_LINE = re.compile(r"[–−-]\s?\d+\s*ball", re.IGNORECASE)


def test_each_of_the_ten_sources_has_at_least_one_exact_tariff_example(manifest):
    sections = {i["section"]: i for i in manifest["items"]}
    with_options = {next(i["section"] for i in manifest["items"] if i["key"] == o["item"]) for o in manifest["penalty_options"]}
    assert with_options == set(sections)  # 10 manba ham


def test_rule_26_has_two_separate_variants_and_no_default(manifest):
    item = next(i for i in manifest["items"] if i["key"] == "nizomlar:26")
    options = [o for o in manifest["penalty_options"] if o["item"] == item["key"]]
    assert sorted(o["points"] for o in options) == [6, 10] and item["default_points"] is None
    ten = next(o for o in options if o["points"] == 10)
    assert ten["written_warning"] is True
    rows, option_rows = importer.build_rows()
    assert "BACHKANA" in next(o for o in option_rows if o["variant_key"] == "nizomlar:26:o1")["condition_text"]


def test_rule_17_and_mevachi_and_warning_precondition_are_kept(manifest):
    rule17 = [o for o in manifest["penalty_options"] if o["item"] == "nizomlar:17"]
    assert sorted(o["points"] for o in rule17) == [6, 10]
    mevachi = [o for o in manifest["penalty_options"] if o["item"].startswith("mevachi")]
    assert {6, 10, 20} <= {o["points"] for o in mevachi}
    assert any(o["target"] == "supplier" and not o["apply_allowed"] for o in mevachi)
    banan = next(o for o in manifest["penalty_options"] if o["item"] == "omborchi:05")
    assert banan["points"] == 6 and banan["gate_lines"] is not None  # "Uch marta ogohlantirilgandan keyin"
    _, option_rows = importer.build_rows()
    assert "Uch marta ogohlantirilgandan keyin" in next(o for o in option_rows if o["variant_key"] == "omborchi:05:o1")["gate_text"]


def test_unresolved_items_have_no_options_and_no_default(manifest):
    for note in manifest["unresolved"]:
        covering = [i for i in manifest["items"] if i["first_line"] <= note["first_line"] and note["last_line"] <= i["last_line"]]
        assert covering, note
    culture_unresolved = next(i for i in manifest["items"] if i["key"] == "madaniyat:12")  # 28–30: miqdor yo'q
    assert culture_unresolved["default_points"] is None
    assert not [o for o in manifest["penalty_options"] if o["item"] == "madaniyat:12"]
    large_theft = next(i for i in manifest["items"] if i["key"] == "nizomlar:23")
    assert [o["points"] for o in manifest["penalty_options"] if o["item"] == "nizomlar:23"] == [6]  # faqat kichik o'g'irlik


def test_order_without_points_item_has_single_confirmed_option_with_precondition(manifest):
    options = [o for o in manifest["penalty_options"] if o["item"] == "nizomlar:11"]
    assert len(options) == 1 and options[0]["points"] == 10 and options[0]["gate_lines"]  # "buyruqda ball ko'rsatilmagan bo'lsa"
    item = next(i for i in manifest["items"] if i["key"] == "nizomlar:11")
    assert item["default_points"] is None  # shart tasdiqlanmaguncha avtomatik emas


# ---------------------------------------------------------------- import (SQLite) --


def _seed_other_data():
    discipline.add_rule(777, "Oldingi nizom", "Mavjud boshqa band", FOUNDER)
    discipline.adjust_bonus_bank(5, 10, "bonus", "daily_evaluation", None)
    discipline.record_daily_grade(5, FOUNDER, "2026-10-01", discipline.GRADE_ALO)


def test_empty_db_import_creates_the_full_catalog_and_changes_no_balances_or_penalties():
    _seed_other_data()
    before = (_count("bonus_bank_ledger"), _count("discipline_penalties"), _count("daily_evaluations"), _count("daily_evaluation_history"))

    result = importer.run_import(apply=True, created_by=FOUNDER, expected_version=importer.import_version())

    assert result["applied"] is True and result["conflicts"] == []
    assert (result["rules_inserted"], result["options_inserted"], result["unresolved"]) == (97, 88, 17)
    assert _count("company_rules", "catalog_kind IS NOT NULL") == 97 and _count("company_rule_penalty_options") == 88
    assert discipline.get_rule(777)["title"] == "Oldingi nizom"  # mavjud boshqa nizom saqlangan
    assert (_count("bonus_bank_ledger"), _count("discipline_penalties"), _count("daily_evaluations"), _count("daily_evaluation_history")) == before
    kinds = discipline_repo.list_catalog_rules()
    assert {k["catalog_kind"] for k in kinds} == {"nizom", "bonus_model", "culture", "checklist"}
    assert next(k for k in kinds if k["rule_number"] == 26)["default_penalty_amount"] is None
    assert next(k for k in kinds if k["rule_number"] == 8)["default_penalty_amount"] == 4  # bir ma'noli band


def test_dry_run_writes_nothing_and_reports_the_same_plan_as_apply():
    dry = importer.run_import(apply=False, created_by=FOUNDER)

    assert (_count("company_rules"), _count("company_rule_penalty_options")) == (0, 0)
    assert dry["applied"] is False and dry["rules_inserted"] == 97 and dry["options_inserted"] == 88

    applied = importer.run_import(apply=True, created_by=FOUNDER, expected_version=dry["version"])
    assert {k: dry[k] for k in ("rules_inserted", "options_inserted", "conflicts", "unresolved")} == {
        k: applied[k] for k in ("rules_inserted", "options_inserted", "conflicts", "unresolved")
    }


def test_repeated_import_is_idempotent_and_creates_no_duplicates():
    version = importer.import_version()
    importer.run_import(apply=True, created_by=FOUNDER, expected_version=version)

    again = importer.run_import(apply=True, created_by=FOUNDER, expected_version=version)

    assert (again["rules_inserted"], again["options_inserted"], again["rules_unchanged"], again["options_unchanged"]) == (0, 0, 97, 88)
    assert (_count("company_rules"), _count("company_rule_penalty_options")) == (97, 88)


def test_parallel_imports_do_not_duplicate():
    version = importer.import_version()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda _: importer.run_import(apply=True, created_by=FOUNDER, expected_version=version), range(4)
        ))

    assert (_count("company_rules"), _count("company_rule_penalty_options")) == (97, 88)
    assert all(r["conflicts"] == [] or all("parallel" in c or "busy" in c for c in r["conflicts"]) for r in results)


def test_conflicting_existing_rule_text_blocks_apply_without_overwriting():
    discipline.add_rule(5, "MINUS BALLGA NOROZILIK BILDIRISH", "Boshqa, qo'lda yozilgan matn", FOUNDER)

    dry = importer.run_import(apply=False, created_by=FOUNDER)
    applied = importer.run_import(apply=True, created_by=FOUNDER, expected_version=dry["version"])

    assert dry["conflicts"] and applied["conflicts"] == dry["conflicts"]  # dry-run va apply bir xil xulosa
    assert applied["applied"] is False
    assert discipline.get_rule(5)["content"] == "Boshqa, qo'lda yozilgan matn"  # ustidan yozilmagan
    assert _count("company_rules") == 1 and _count("company_rule_penalty_options") == 0  # hech narsa import bo'lmagan


def test_existing_identical_legacy_rule_only_gets_empty_metadata_filled():
    rows, _ = importer.build_rows()
    row = next(r for r in rows if r["rule_number"] == 8)
    discipline.add_rule(8, row["title"], row["content"], FOUNDER)
    discipline_repo.set_rule_penalty_amount(8, row["default_penalty_amount"])

    result = importer.run_import(apply=True, created_by=FOUNDER, expected_version=importer.import_version())

    assert result["conflicts"] == [] and result["rules_adopted"] == 1
    adopted = discipline.get_rule(8)
    assert (adopted["catalog_kind"], adopted["source_key"]) == ("nizom", "nizomlar:08") and adopted["content"] == row["content"]


def test_existing_different_variant_is_a_conflict_and_nothing_is_written():
    importer.run_import(apply=True, created_by=FOUNDER, expected_version=importer.import_version())
    conn = get_connection()
    try:
        conn.execute("UPDATE company_rule_penalty_options SET points = 99 WHERE variant_key = 'nizomlar:26:o1'")
        conn.execute("DELETE FROM company_rule_penalty_options WHERE variant_key = 'oshpaz:01:o1'")
        conn.commit()
    finally:
        conn.close()

    result = importer.run_import(apply=True, created_by=FOUNDER, expected_version=importer.import_version())

    assert any("nizomlar:26:o1" in c for c in result["conflicts"]) and result["applied"] is False
    assert _count("company_rule_penalty_options", "variant_key = 'oshpaz:01:o1'") == 0  # konfliktda to'ldirilmaydi


def test_write_error_rolls_back_the_whole_catalog_and_retry_succeeds():
    conn = get_connection()
    try:
        conn.execute(
            "CREATE TRIGGER break_options BEFORE INSERT ON company_rule_penalty_options "
            "BEGIN SELECT RAISE(ABORT, 'sinov: yozuv xatosi'); END"
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError):
        importer.run_import(apply=True, created_by=FOUNDER, expected_version=importer.import_version())

    assert (_count("company_rules"), _count("company_rule_penalty_options")) == (0, 0)  # yarim katalog qolmagan
    conn = get_connection()
    try:
        conn.execute("DROP TRIGGER break_options")
        conn.commit()
    finally:
        conn.close()
    result = importer.run_import(apply=True, created_by=FOUNDER, expected_version=importer.import_version())
    assert result["applied"] and (_count("company_rules"), _count("company_rule_penalty_options")) == (97, 88)


def test_wrong_source_hash_or_unapproved_version_blocks_apply(monkeypatch, tmp_path):
    with pytest.raises(importer.ImportBlocked):
        importer.run_import(apply=True, created_by=FOUNDER, expected_version="000000000000-v1")
    with pytest.raises(importer.ImportBlocked):
        importer.run_import(apply=True, created_by=FOUNDER, expected_version=None)

    tampered = tmp_path / "source.txt"
    tampered.write_bytes(importer.SOURCE_PATH.read_bytes().replace(b"-10 ball", b"-11 ball", 1) + b" ")
    monkeypatch.setattr(importer, "SOURCE_PATH", tampered)
    with pytest.raises(importer.ImportBlocked):
        importer.run_import(apply=True, created_by=FOUNDER, expected_version=importer.import_version())
    assert _count("company_rules") == 0


def test_importer_writes_rules_only_never_penalties_grades_or_notifications():
    importer.run_import(apply=True, created_by=FOUNDER, expected_version=importer.import_version())

    assert _count("discipline_penalties") == 0 and _count("bonus_bank_ledger") == 0 and _count("daily_evaluations") == 0


# ---------------------------------------------- apply_penalty himoyasi va o'rganish --


def _import():
    importer.run_import(apply=True, created_by=FOUNDER, expected_version=importer.import_version())


def _option(variant_key: str) -> dict:
    return next(o for o in discipline_repo.list_penalty_options() if o["variant_key"] == variant_key)


def test_multi_variant_rule_requires_a_variant_and_exact_points():
    _import()
    six, ten = _option("nizomlar:26:o1"), _option("nizomlar:26:o2")

    with pytest.raises(ValueError):
        discipline.apply_penalty(7, FOUNDER, "2026-10-19", 6, 26, None, None)  # variantsiz
    with pytest.raises(ValueError):
        discipline.apply_penalty(7, FOUNDER, "2026-10-19", 10, 26, None, None, option_id=six["id"])  # variantga mos emas
    with pytest.raises(ValueError):
        discipline.apply_penalty(7, FOUNDER, "2026-10-19", 20, 26, None, None)  # umumiy 10/20/30 ro'yxati yetmaydi
    assert discipline.get_salary(7)["bonus_bank"] == 0 and _count("discipline_penalties") == 0

    done = discipline.apply_penalty(7, FOUNDER, "2026-10-19", 6, 26, "izoh", None, option_id=six["id"])
    assert done["bonus_bank_ledger" if False else "bonus_bank_balance"] == -6
    assert "variant=nizomlar:26:o1" in discipline_repo.get_penalty(done["penalty_id"])["ai_note"]
    assert ten["points"] == 10


def test_generic_amounts_do_not_bypass_catalog_rules_without_confirmed_points():
    _import()
    unresolved = discipline_repo.get_rule_by_number(10_101 + 11)  # madaniyat:12 — miqdorsiz
    assert unresolved["default_penalty_amount"] is None

    for amount in (10, 20, 30):
        with pytest.raises(ValueError):
            discipline.apply_penalty(7, FOUNDER, "2026-10-19", amount, unresolved["rule_number"], None, None)
        with pytest.raises(ValueError):
            discipline.apply_penalty(7, FOUNDER, "2026-10-19", amount, 1, None, None)  # 1-nizom: ball yo'q
    assert _count("discipline_penalties") == 0


def test_single_option_rule_accepts_only_its_own_confirmed_amount():
    _import()
    discipline.apply_penalty(7, FOUNDER, "2026-10-19", 4, 8, None, None)  # 8-nizom: –4
    with pytest.raises(ValueError):
        discipline.apply_penalty(7, FOUNDER, "2026-10-19", 10, 8, None, None)
    assert discipline.get_salary(7)["bonus_bank"] == -4


def test_options_for_other_persons_cannot_be_applied_to_an_employee():
    _import()
    supplier = _option("mevachi:03:o2")
    assert supplier["target"] == "supplier" and supplier["apply_allowed"] == 0

    with pytest.raises(ValueError):
        discipline.apply_penalty(7, FOUNDER, "2026-10-19", supplier["points"], supplier["rule_number"], None, None, option_id=supplier["id"])


def test_option_of_another_rule_is_rejected():
    _import()
    other = _option("nizomlar:17:o1")

    with pytest.raises(ValueError):
        discipline.apply_penalty(7, FOUNDER, "2026-10-19", other["points"], 26, None, None, option_id=other["id"])


def test_legacy_rules_without_catalog_metadata_keep_the_old_behaviour():
    discipline.add_rule(900, "Eski band", "Matn", FOUNDER)
    assert discipline.apply_penalty(7, FOUNDER, "2026-10-19", 10, 900, None, None)["bonus_bank_balance"] == -10
    discipline.set_rule_penalty_amount(900, 7, FOUNDER)
    assert discipline.apply_penalty(7, FOUNDER, "2026-10-19", 7, 900, None, None)["bonus_bank_balance"] == -17


def test_catalog_point_values_cannot_be_overridden_by_set_rule_penalty_amount():
    _import()
    with pytest.raises(ValueError):
        discipline.set_rule_penalty_amount(8, 99, FOUNDER)
    assert discipline.get_rule(8)["default_penalty_amount"] == 4


def test_rule_learning_only_uses_official_rules_not_culture_or_checklists():
    from services import rule_learning

    _import()
    numbers = {rule["rule_number"] for rule in rule_learning._remaining_active_rules(123)}

    assert numbers == set(range(1, 27))  # bonus modeli, madaniyat va 8 chek-list majburan o'qitilmaydi
    assert len(discipline_repo.list_learning_rules()) == 26


def test_long_text_pages_never_lose_content_and_fit_telegram_limit():
    long_text = "\n".join(f"Satr {i} " + "x" * 90 for i in range(200))
    pages = discipline.split_text_pages(long_text, limit=1000)

    assert all(len(page) <= 1000 for page in pages) and len(pages) > 1
    assert "\n".join(pages) == long_text
    assert discipline.split_text_pages("qisqa") == ["qisqa"]
    one_line = "y" * 2500
    assert "".join(discipline.split_text_pages(one_line, limit=1000)) == one_line


def test_rule_reference_finds_exact_rule_but_not_plain_numbers():
    _import()
    assert discipline.parse_rule_reference("26-nizomga amal qilmadi") == 26
    assert discipline.parse_rule_reference("nizom 17 buzildi") == 17
    assert discipline.parse_rule_reference("10 daqiqa kechikdi") is None
    assert discipline.parse_rule_reference("99-nizom") is None


def test_catalog_entries_cover_all_sources_and_exclude_only_notes_and_bonus_model():
    _import()
    entries = discipline.get_catalog_entries()
    sources = discipline.list_catalog_sources(entries)

    assert [s["section"] for s in sources] == list(discipline.SOURCE_ORDER)
    assert len(entries) == 97 - 1 - 3  # bonus modeli va 3 ta "Eslatma:" izohi nomzod emas
    rule26 = discipline.get_catalog_entry(26)
    assert rule26["amount_status"] == "options" and rule26["display_number"] == 26
    assert discipline.get_catalog_entry(10_101 + 11)["amount_status"] == "none"
    assert discipline.entry_amount_text(discipline.get_catalog_entry(10_101 + 11)) == "Ball miqdori belgilanmagan"
