"""``services/photo_scene.py`` — deterministik crop/rang/ob-havo
effekt kompozitsiyasi uchun testlar (haqiqiy kataloglangan fotolar
bilan, tarmoqqa chiqmasdan)."""

from PIL import Image

from services import photo_catalog as pc
from services import photo_scene as ps


def _first_asset() -> pc.PhotoAsset:
    catalog = pc.get_default_catalog()
    assets = catalog.all_assets()
    assert assets, "test uchun kamida bitta kataloglangan foto kerak"
    return assets[0]


def test_render_photo_background_produces_correct_size():
    asset = _first_asset()
    image = ps.render_photo_background(asset, asset.weather_tag, asset.time_of_day, "variant1")
    assert image.size == (ps.IMAGE_SIZE, ps.IMAGE_SIZE)
    assert image.mode == "RGB"


def test_render_photo_background_is_deterministic_for_same_variant_id():
    asset = _first_asset()
    first = ps.render_photo_background(asset, asset.weather_tag, asset.time_of_day, "same_variant")
    second = ps.render_photo_background(asset, asset.weather_tag, asset.time_of_day, "same_variant")
    assert list(first.getdata()) == list(second.getdata())


def test_render_photo_background_differs_across_variant_ids():
    asset = _first_asset()
    first = ps.render_photo_background(asset, asset.weather_tag, asset.time_of_day, "variant_a")
    second = ps.render_photo_background(asset, asset.weather_tag, asset.time_of_day, "variant_b")
    assert list(first.getdata()) != list(second.getdata())


def test_exact_weather_match_skips_synthetic_overlay(monkeypatch):
    asset = _first_asset()  # weather_tag mos keladi -> overlay chaqirilmasligi kerak
    called = False

    def _fake_overlay(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(ps, "_apply_weather_overlay", _fake_overlay)
    ps.render_photo_background(asset, asset.weather_tag, asset.time_of_day, "v1")
    assert called is False


def test_mismatched_weather_triggers_synthetic_overlay(monkeypatch):
    asset = _first_asset()
    mismatched_category = "rain" if asset.weather_tag != "rain" else "snow"
    called = False

    def _fake_overlay(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(ps, "_apply_weather_overlay", _fake_overlay)
    ps.render_photo_background(asset, mismatched_category, asset.time_of_day, "v1")
    assert called is True


def test_deterministic_square_crop_never_exceeds_source_bounds():
    asset = _first_asset()
    photo_path = pc._ASSETS_DIR / asset.file_path
    photo = Image.open(photo_path).convert("RGB")
    rng = ps._seed(asset.photo_id, "crop_test")
    cropped = ps._deterministic_square_crop(photo, rng)
    assert cropped.width == cropped.height
    assert cropped.width <= min(photo.size)
