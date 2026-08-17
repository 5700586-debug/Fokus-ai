"""``services/photo_catalog.py`` — manifest yuklash, checksum
tekshirish va deterministik tanlov uchun testlar."""

import json
from datetime import date, timedelta

import pytest

from services import photo_catalog as pc


def _write_manifest(tmp_path, photos):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"photos": photos}), encoding="utf-8")
    return manifest_path


def _fake_photo_entry(photo_id, season="bahor", weather_tag="clear", time_of_day="morning", checksum="deadbeef"):
    return {
        "photo_id": photo_id,
        "season": season,
        "weather_tag": weather_tag,
        "time_of_day": time_of_day,
        "file_path": f"originals/{photo_id}.jpg",
        "source": "openverse",
        "source_id": "abc123",
        "photographer": "Test Photographer",
        "photographer_url": "https://example.com",
        "source_url": "https://example.com/photo",
        "license": "cc0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "checksum_sha256": checksum,
        "downloaded_at": "2026-01-01T00:00:00+00:00",
    }


def test_missing_manifest_file_returns_empty_catalog(tmp_path):
    catalog = pc.LocalPhotoCatalog(manifest_path=tmp_path / "does_not_exist.json")
    assert catalog.all_assets() == []


def test_malformed_manifest_returns_empty_catalog_without_crashing(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("not valid json {{{", encoding="utf-8")
    catalog = pc.LocalPhotoCatalog(manifest_path=manifest_path)
    assert catalog.all_assets() == []


def test_entry_with_missing_file_is_skipped_not_crashed(tmp_path):
    manifest_path = _write_manifest(tmp_path, [_fake_photo_entry("ghost")])
    catalog = pc.LocalPhotoCatalog(manifest_path=manifest_path, verify_checksums=True)
    assert catalog.all_assets() == []


def test_checksum_mismatch_excludes_entry(tmp_path, monkeypatch):
    (tmp_path / "originals").mkdir()
    photo_file = tmp_path / "originals" / "tampered.jpg"
    photo_file.write_bytes(b"real content")

    manifest_path = _write_manifest(tmp_path, [_fake_photo_entry("tampered", checksum="wrong_checksum")])
    monkeypatch.setattr(pc, "_ASSETS_DIR", tmp_path)
    catalog = pc.LocalPhotoCatalog(manifest_path=manifest_path, verify_checksums=True)
    assert catalog.all_assets() == []


def test_valid_checksum_is_accepted(tmp_path, monkeypatch):
    import hashlib

    (tmp_path / "originals").mkdir()
    photo_file = tmp_path / "originals" / "good.jpg"
    photo_file.write_bytes(b"real content")
    checksum = hashlib.sha256(b"real content").hexdigest()

    manifest_path = _write_manifest(tmp_path, [_fake_photo_entry("good", checksum=checksum)])
    monkeypatch.setattr(pc, "_ASSETS_DIR", tmp_path)
    catalog = pc.LocalPhotoCatalog(manifest_path=manifest_path, verify_checksums=True)
    assert len(catalog.all_assets()) == 1


def test_list_candidates_matches_exact_season_weather_time():
    real_catalog = pc.get_default_catalog()
    candidates = real_catalog.list_candidates("bahor", "clear", "morning")
    assert any(c.photo_id == "spring_meadow_oregon" for c in candidates)


def test_list_candidates_matches_universal_season_tag():
    real_catalog = pc.get_default_catalog()
    candidates = real_catalog.list_candidates("kuz", "windy", "morning")
    assert any(c.photo_id == "windy_wheat_field" for c in candidates)


def test_list_candidates_returns_empty_for_unknown_combo():
    real_catalog = pc.get_default_catalog()
    candidates = real_catalog.list_candidates("qish", "drizzle", "morning")
    assert candidates == [] or all(c.weather_tag == "season_default" for c in candidates)


# ------------------------------------------------------------ deterministik --


def test_variant_id_is_pure_function_of_inputs():
    d = date(2026, 6, 1)
    assert pc.variant_id_for("photo_a", d) == pc.variant_id_for("photo_a", d)


def test_variant_id_differs_by_date():
    assert pc.variant_id_for("photo_a", date(2026, 6, 1)) != pc.variant_id_for("photo_a", date(2026, 6, 2))


def test_variant_id_differs_by_photo():
    d = date(2026, 6, 1)
    assert pc.variant_id_for("photo_a", d) != pc.variant_id_for("photo_b", d)


def test_select_photo_is_deterministic_for_same_date():
    catalog = pc.get_default_catalog()
    d = date(2026, 5, 1)
    first = pc.select_photo(catalog, "bahor", "clear", "morning", d, [])
    second = pc.select_photo(catalog, "bahor", "clear", "morning", d, [])
    assert first == second


def test_select_photo_returns_none_when_no_candidates():
    catalog = pc.get_default_catalog()
    result = pc.select_photo(catalog, "qish", "drizzle", "morning", date(2026, 1, 1), [])
    # Yoki mos foto yo'q (None), yoki fasl-standart fallback orqali topildi —
    # ikkalasi ham xato emas, faqat mavjud katalogga bog'liq.
    assert result is None or result[0].weather_tag == "season_default"


def test_select_photo_excludes_recent_photo_ids_when_alternatives_exist(tmp_path, monkeypatch):
    import hashlib

    (tmp_path / "originals").mkdir()
    for name in ("a", "b"):
        (tmp_path / "originals" / f"{name}.jpg").write_bytes(name.encode())
    checksum_a = hashlib.sha256(b"a").hexdigest()
    checksum_b = hashlib.sha256(b"b").hexdigest()
    manifest_path = _write_manifest(
        tmp_path,
        [_fake_photo_entry("a", checksum=checksum_a), _fake_photo_entry("b", checksum=checksum_b)],
    )
    monkeypatch.setattr(pc, "_ASSETS_DIR", tmp_path)
    catalog = pc.LocalPhotoCatalog(manifest_path=manifest_path)

    selection = pc.select_photo(catalog, "bahor", "clear", "morning", date(2026, 1, 1), recent_photo_ids=["a"])
    assert selection is not None
    assert selection[0].photo_id == "b"


def test_total_real_variant_count_reflects_actual_catalog_size():
    catalog = pc.get_default_catalog()
    expected = len(catalog.all_assets()) * pc.VARIANTS_PER_PHOTO
    assert pc.total_real_variant_count(catalog) == expected
    # Hech qachon to'qib chiqarilgan katta raqam emas — haqiqiy foto
    # soniga chiziqli bog'liq (fantastik "millionlab" son emas).
    assert pc.total_real_variant_count(catalog) < 100_000
