from datetime import date

import pytest
from PIL import Image

from services import saturn_scene as scene
from services import saturn_season
from services import saturn_weather_scene as ws

_ALL_SEASONS = [saturn_season.SPRING, saturn_season.SUMMER, saturn_season.AUTUMN, saturn_season.WINTER]
_ALL_CATEGORIES = list(ws.PRIORITY_ORDER)
_ALL_TIMES = [scene.TIME_MORNING, scene.TIME_NIGHT]


def test_all_season_category_time_combinations_render_at_correct_size():
    for season in _ALL_SEASONS:
        for category in _ALL_CATEGORIES:
            for time_of_day in _ALL_TIMES:
                for variant in range(scene.NUM_VARIANTS):
                    image = scene.render_background(season, category, time_of_day, variant)
                    assert isinstance(image, Image.Image)
                    assert image.size == (scene.IMAGE_SIZE, scene.IMAGE_SIZE)


def test_variant_index_is_a_pure_function_of_date():
    d = date(2026, 6, 15)
    assert scene.variant_index(d) == scene.variant_index(d)


def test_variant_index_never_repeats_on_consecutive_days():
    for ordinal in range(1, 400):
        d1 = date.fromordinal(ordinal)
        d2 = date.fromordinal(ordinal + 1)
        assert scene.variant_index(d1) != scene.variant_index(d2)


def test_variant_index_with_offset_also_never_repeats_on_consecutive_days():
    for ordinal in range(1, 400):
        d1 = date.fromordinal(ordinal)
        d2 = date.fromordinal(ordinal + 1)
        assert scene.variant_index(d1, offset=1) != scene.variant_index(d2, offset=1)


def test_no_tornado_drawing_function_exists_anywhere_in_the_module():
    """Vizual 'oddiy shamol uchun tornado ishlatilmaydi' talabi: modulda
    umuman tornado/bo'ron chizadigan funksiya yo'q — shamol faqat
    ``_paint_wind_leaves`` (uchayotgan barglar) va egilgan daraxt bilan
    ko'rsatiladi."""
    function_names = [name for name in dir(scene) if name.startswith("_paint")]
    assert not any("tornado" in name or "storm" in name for name in function_names)


def test_windy_category_uses_leaves_and_bent_tree_not_lightning():
    """Shamolli sahna chaqmoq (momaqaldiroq uchun ishlatiladigan
    funksiya) chaqirmaydi — faqat cho'zilgan bulut va uchayotgan
    barglar bilan yengil harakat hissi beriladi."""
    import unittest.mock as mock

    with mock.patch.object(scene, "_paint_lightning") as fake_lightning, \
         mock.patch.object(scene, "_paint_wind_leaves", wraps=scene._paint_wind_leaves) as fake_leaves:
        scene.render_background(saturn_season.AUTUMN, ws.CATEGORY_WINDY, scene.TIME_MORNING, 0)

    fake_lightning.assert_not_called()
    fake_leaves.assert_called_once()


def test_snowy_winter_night_scene_differs_visibly_from_clear_summer_night_scene():
    """Fasl/ob-havo darhol tanib olinishi kerak — ikkita ancha farqli
    sahna (qishki qorli tun vs. yozgi ochiq tun) piksel darajasida ham
    sezilarli darajada farq qilishi kerak (bo'sh, bir xil fon emas)."""
    winter_snow_night = scene.render_background(saturn_season.WINTER, ws.CATEGORY_SNOW, scene.TIME_NIGHT, 0)
    summer_clear_night = scene.render_background(saturn_season.SUMMER, ws.CATEGORY_CLEAR, scene.TIME_NIGHT, 0)

    winter_pixels = list(winter_snow_night.getdata())
    summer_pixels = list(summer_clear_night.getdata())
    differing = sum(1 for a, b in zip(winter_pixels, summer_pixels) if a != b)

    assert differing > len(winter_pixels) * 0.1
