"""Saturn brand lockup (AIM logotipi + "SATURN" yozuvi) uchun maqsadli
testlar: logotip assetining o'zi, nisbat, brend rangi va rasmdagi
joylashuv."""

from pathlib import Path

import pytest
from PIL import Image

from services import saturn_image

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


_LOGO_ASSET_PATH = Path(__file__).resolve().parent.parent / "assets" / "branding" / "saturn_logo.png"


def test_logo_asset_file_exists():
    assert _LOGO_ASSET_PATH.is_file()


def test_logo_asset_has_alpha_channel_and_transparent_background():
    logo = Image.open(_LOGO_ASSET_PATH)
    assert logo.mode == "RGBA"

    # Burchaklar (fon) shaffof bo'lishi kerak — telefon interfeysi/qora
    # joylar va oq fon olib tashlangan.
    corners = [(0, 0), (logo.width - 1, 0), (0, logo.height - 1), (logo.width - 1, logo.height - 1)]
    for x, y in corners:
        alpha = logo.getpixel((x, y))[3]
        assert alpha < 20, f"corner ({x},{y}) alpha={alpha}, fon shaffof emas"


def test_logo_asset_has_a_solid_red_core():
    logo = Image.open(_LOGO_ASSET_PATH).convert("RGBA")
    cx, cy = logo.width // 2, logo.height // 2
    r, g, b, a = logo.getpixel((cx, cy - logo.height // 4))
    assert a > 200
    assert r > 180
    assert g < 60
    assert b < 60


def test_logo_asset_aspect_ratio_is_roughly_square():
    """Manba logotip doiraviy (AIM belgisi) — nisbat cho'zilmagan yoki
    siqilmagan bo'lishi kerak."""
    logo = Image.open(_LOGO_ASSET_PATH)
    ratio = logo.width / logo.height
    assert 0.9 <= ratio <= 1.1, ratio


def test_load_logo_preserves_source_aspect_ratio():
    """``_load_logo`` faqat balandlikka moslab o'lchamni o'zgartiradi —
    nisbat (eni/bo'yi) manba fayl bilan bir xil qoladi (cho'zilmaydi)."""
    source = Image.open(_LOGO_ASSET_PATH)
    source_ratio = source.width / source.height

    loaded = saturn_image._load_logo()
    assert loaded is not None
    assert loaded.height == saturn_image._LOGO_HEIGHT
    loaded_ratio = loaded.width / loaded.height
    assert abs(loaded_ratio - source_ratio) < 0.02


def test_load_logo_returns_none_when_path_missing(monkeypatch):
    monkeypatch.setattr(saturn_image, "SATURN_LOGO_PATH", "/no/such/file.png")
    assert saturn_image._load_logo() is None


def test_load_logo_returns_none_when_file_corrupt(monkeypatch, tmp_path):
    bad_file = tmp_path / "not_an_image.png"
    bad_file.write_bytes(b"bu rasm emas")
    monkeypatch.setattr(saturn_image, "SATURN_LOGO_PATH", str(bad_file))
    assert saturn_image._load_logo() is None


def test_default_saturn_logo_path_points_to_bundled_asset():
    import config

    assert Path(config.SATURN_LOGO_PATH) == _LOGO_ASSET_PATH


# ------------------------------------------------------- brend rangi --


def test_brand_red_matches_the_logo_assets_actual_red():
    """``_BRAND_RED`` konstantasi bank/logotip fayldan aniq olingan
    qizil bilan yaqin (JPEG/PNG siqilish sabab ozgina farq mumkin,
    lekin sezilarli darajada emas)."""
    logo = Image.open(_LOGO_ASSET_PATH).convert("RGBA")
    cx = logo.width // 2
    cy = logo.height // 2 - logo.height // 4
    r, g, b, _a = logo.getpixel((cx, cy))
    ref_r, ref_g, ref_b = saturn_image._BRAND_RED
    assert abs(r - ref_r) <= 15
    assert abs(g - ref_g) <= 15
    assert abs(b - ref_b) <= 15


def test_saturn_wordmark_pixel_color_matches_brand_red_in_rendered_image():
    """Rasmda chizilgan "SATURN" matni piksel darajasida ham aynan
    ``_BRAND_RED`` rangida ekanini tekshiradi (tong yoki tun fonidan
    qat'i nazar)."""
    import io

    data = saturn_image.render_morning_image("Test.", season="yoz", weather_category="clear")
    image = Image.open(io.BytesIO(data)).convert("RGB")

    # "SATURN" matni logotipdan o'ngda, lockup ichida — shu hududni
    # skanerlab, brend qizil rangidagi piksel borligini tasdiqlaymiz.
    found = False
    search_top = saturn_image._MARGIN
    search_bottom = saturn_image._MARGIN + saturn_image._LOGO_HEIGHT
    search_left = saturn_image._MARGIN + saturn_image._LOGO_HEIGHT
    search_right = search_left + 250
    for y in range(search_top, min(search_bottom, image.height), 3):
        for x in range(search_left, min(search_right, image.width), 3):
            r, g, b = image.getpixel((x, y))
            if abs(r - saturn_image._BRAND_RED[0]) <= 10 and abs(g - saturn_image._BRAND_RED[1]) <= 10 and abs(b - saturn_image._BRAND_RED[2]) <= 10:
                found = True
                break
        if found:
            break
    assert found, "SATURN yozuvi brend qizil rangida topilmadi"


# --------------------------------------------------- lockup joylashuvi --


def test_brand_lockup_is_in_the_same_position_for_morning_and_night():
    """Logotip+SATURN joylashuvi va o'lchami tong va tun rasmlarida bir
    xil (konstantalar orqali kafolatlangan, lekin ikkalasi ham
    xatosiz render bo'lishini tasdiqlaydi)."""
    import io

    morning = Image.open(io.BytesIO(
        saturn_image.render_morning_image("Test.", season="qish", weather_category="snow")
    ))
    night = Image.open(io.BytesIO(
        saturn_image.render_night_image("Test.", season="qish", weather_category="snow")
    ))
    assert morning.size == night.size == (saturn_image.IMAGE_SIZE, saturn_image.IMAGE_SIZE)


def test_logo_height_within_requested_range():
    assert 80 <= saturn_image._LOGO_HEIGHT <= 90


def test_logo_text_gap_within_requested_range():
    assert 15 <= saturn_image._LOGO_TEXT_GAP <= 20
