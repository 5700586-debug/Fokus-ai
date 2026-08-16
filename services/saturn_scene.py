"""Fasl + ob-havo + kun vaqtiga mos original vizual "sahna" (fon).

Bu modul HECH QANDAY tashqi/internet rasm ishlatmaydi — hammasi
dasturiy ravishda (Pillow bilan) chizilgan: osmon gradienti, ufq,
o'simlik/qor/yomg'ir/tuman kabi ob-havo unsurlari va oddiy, neytral
do'kon shakli. Bular ASL, mualliflik huquqi muammosiz assetlar.

Muhim qoida: oddiy shamol uchun bo'ron/tornado tasviri ISHLATILMAYDI —
faqat uchayotgan barglar, cho'zilgan bulutlar va yengil egilgan
daraxt bilan "yengil harakat" hissi beriladi (qarang
``services/saturn_weather_scene.py`` docstringi).

Har bir (fasl, ob-havo kategoriyasi, kun vaqti) kombinatsiyasi uchun
``NUM_VARIANTS`` ta vizual variant bor — variant ``local_date`` asosida
DETERMINISTIK tanlanadi (worker qayta ishga tushsa ham bir xil sana
bir xil rasmni beradi), va ketma-ket ikki kun HECH QACHON bir xil
variant olmaydi (qarang ``variant_index``).
"""

import hashlib
import random
from datetime import date

from PIL import Image, ImageDraw

IMAGE_SIZE = 1080
NUM_VARIANTS = 3

TIME_MORNING = "morning"
TIME_NIGHT = "night"

# -------------------------------------------------------------- palitralar --
# (osmon_yuqori, osmon_pastki, yer/o't rangi, barg/urg'u rangi)
_MORNING_PALETTES: dict[str, tuple] = {
    "bahor": ((198, 233, 214), (255, 232, 176), (108, 178, 96), (150, 210, 120)),
    "yoz": ((255, 236, 150), (255, 172, 108), (188, 172, 88), (232, 200, 90)),
    "kuz": ((255, 208, 150), (214, 134, 86), (146, 96, 54), (198, 118, 48)),
    "qish": ((222, 234, 246), (198, 214, 236), (232, 238, 245), (206, 222, 240)),
}

_NIGHT_PALETTES: dict[str, tuple] = {
    "bahor": ((10, 34, 46), (24, 54, 64), (16, 36, 30)),
    "yoz": ((8, 10, 34), (20, 24, 58), (10, 12, 30)),
    "kuz": ((20, 15, 28), (44, 30, 34), (24, 16, 18)),
    "qish": ((8, 16, 36), (18, 28, 52), (20, 26, 42)),
}


def variant_index(local_date: date, offset: int = 0) -> int:
    """``local_date.toordinal()`` asosida — sof sana funksiyasi (worker
    qayta tushsa ham o'zgarmaydi), va ketma-ket kunlar hech qachon bir
    xil qiymat olmaydi (``NUM_VARIANTS > 1`` bo'lgani uchun)."""
    return (local_date.toordinal() + offset) % NUM_VARIANTS


def _seed(season: str, category: str, time_of_day: str, variant: int) -> random.Random:
    key = f"{season}|{category}|{time_of_day}|{variant}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return random.Random(int(digest, 16))


def _vertical_gradient(top_rgb, bottom_rgb) -> Image.Image:
    image = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), top_rgb)
    draw = ImageDraw.Draw(image)
    for y in range(IMAGE_SIZE):
        ratio = y / (IMAGE_SIZE - 1)
        row_color = tuple(
            int(top_rgb[c] + (bottom_rgb[c] - top_rgb[c]) * ratio) for c in range(3)
        )
        draw.line([(0, y), (IMAGE_SIZE, y)], fill=row_color)
    return image


def _soft_glow(image: Image.Image, center, radius: int, color, max_alpha: int = 60) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for step in range(radius, 0, -8):
        alpha = int(max_alpha * (1 - step / radius))
        overlay_draw.ellipse(
            [center[0] - step, center[1] - step, center[0] + step, center[1] + step],
            fill=(*color, alpha),
        )
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"), (0, 0))


_HORIZON_Y = 960

# Matn "glass card"i (qarang ``services/saturn_image.py``) taxminan
# Y 370-850 oralig'ini egallaydi. Ko'krak (daraxt) va do'kon shakli
# card ostida kesilib qolmasligi uchun ATAYLAB shu chegaradan pastda
# (kamida ~20px zaxira bilan) chiziladi.
_CARD_CLEAR_Y = 855


def _paint_ground(image: Image.Image, ground_color, rng: random.Random, snowy: bool = False) -> None:
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, _HORIZON_Y, IMAGE_SIZE, IMAGE_SIZE], fill=ground_color)
    # Yumshoq, tekis bo'lmagan ufq chizig'i — bir nechta past tepalik.
    hill_color = tuple(max(0, c - 18) for c in ground_color)
    points = [(0, _HORIZON_Y)]
    x = 0
    while x <= IMAGE_SIZE:
        x += rng.randint(90, 160)
        y = _HORIZON_Y - rng.randint(0, 22)
        points.append((min(x, IMAGE_SIZE), y))
    points.append((IMAGE_SIZE, _HORIZON_Y))
    draw.polygon(points, fill=hill_color)
    if snowy:
        draw.rectangle([0, _HORIZON_Y, IMAGE_SIZE, IMAGE_SIZE], fill=ground_color)


def _paint_shop_silhouette(image: Image.Image, rng: random.Random, dark: bool) -> None:
    """Oddiy, neytral chakana do'kon shakli — hech qanday brend/logotip
    matni yo'q, faqat umumiy shakl (devor, tom, deraza yorug'i). Tom
    uchi ATAYLAB ``_CARD_CLEAR_Y``dan pastda boshlanadi — markazdagi
    matn "glass card"i bilan hech qachon kesishmaydi."""
    draw = ImageDraw.Draw(image)
    width = 190
    roof_apex_y = _CARD_CLEAR_Y + 20
    wall_top_y = roof_apex_y + 24
    wall_bottom_y = wall_top_y + 75
    # O'ng chetdan biroz ichkariroq — pastki-o'ng burchakdagi "Fokus AI"
    # yozuvi bilan gorizontal kesishmasligi uchun.
    left = IMAGE_SIZE - width - 200

    wall_color = (58, 46, 40) if dark else (150, 118, 96)
    roof_color = (40, 32, 28) if dark else (110, 80, 62)
    window_color = (255, 214, 140) if dark else (255, 250, 230)

    draw.rectangle([left, wall_top_y, left + width, wall_bottom_y], fill=wall_color)
    draw.polygon(
        [(left - 12, wall_top_y), (left + width / 2, roof_apex_y), (left + width + 12, wall_top_y)],
        fill=roof_color,
    )
    window_w, window_h = 32, 32
    for wx in (left + 22, left + width - 22 - window_w):
        draw.rectangle(
            [wx, wall_top_y + 18, wx + window_w, wall_top_y + 18 + window_h], fill=window_color
        )
    door_w = 34
    draw.rectangle(
        [left + width / 2 - door_w / 2, wall_top_y + 40, left + width / 2 + door_w / 2, wall_bottom_y],
        fill=(30, 24, 20) if dark else (90, 66, 50),
    )


def _paint_tree_or_bush(image: Image.Image, rng: random.Random, foliage_color, bent: bool = False) -> None:
    """Kichik daraxt/butazor — tepasi ATAYLAB ``_CARD_CLEAR_Y``dan
    pastda qoladi (qarang ``_paint_shop_silhouette`` izohi)."""
    draw = ImageDraw.Draw(image)
    base_x = rng.randint(70, 150)
    base_y = _HORIZON_Y + 15
    trunk_h = rng.randint(30, 48)
    lean = 20 if bent else 4
    draw.line(
        [(base_x, base_y), (base_x + lean, base_y - trunk_h)],
        fill=(90, 62, 40), width=8,
    )
    crown_center = (base_x + lean, base_y - trunk_h - 8)
    for i in range(3):
        offset = (rng.randint(-14, 14), rng.randint(-6, 6))
        radius = rng.randint(18, 27)
        draw.ellipse(
            [
                crown_center[0] + offset[0] - radius, crown_center[1] + offset[1] - radius,
                crown_center[0] + offset[0] + radius, crown_center[1] + offset[1] + radius,
            ],
            fill=foliage_color,
        )


def _paint_sun(image: Image.Image, rng: random.Random, center=(860, 200)) -> None:
    _soft_glow(image, center, radius=260, color=(255, 250, 210), max_alpha=70)
    draw = ImageDraw.Draw(image)
    draw.ellipse(
        [center[0] - 58, center[1] - 58, center[0] + 58, center[1] + 58],
        fill=(255, 244, 200),
    )


def _paint_moon_and_stars(image: Image.Image, rng: random.Random) -> None:
    _soft_glow(image, (860, 190), radius=170, color=(230, 235, 250), max_alpha=45)
    draw = ImageDraw.Draw(image)
    draw.ellipse([810, 150, 900, 240], fill=(235, 238, 248))
    draw.ellipse([826, 148, 906, 228], fill=(13, 27, 58))  # hilol effekti

    for _ in range(24):
        x = rng.randint(40, IMAGE_SIZE - 40)
        y = rng.choice([rng.randint(60, 340), rng.randint(560, 700)])
        radius = rng.choice([1, 1, 2])
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(255, 255, 255))


def _paint_clouds(image: Image.Image, rng: random.Random, count: int, color, stretched: bool = False, top: int = 120, bottom: int = 400) -> None:
    draw = ImageDraw.Draw(image)
    for _ in range(count):
        cx = rng.randint(60, IMAGE_SIZE - 60)
        cy = rng.randint(top, bottom)
        stretch = rng.uniform(2.4, 3.4) if stretched else 1.0
        for _ in range(4):
            rx = rng.randint(40, 70)
            ry = int(rx * 0.6)
            ox = rng.randint(-70, 70)
            oy = rng.randint(-14, 14)
            bbox_w = int(rx * stretch)
            draw.ellipse([cx + ox - bbox_w, cy + oy - ry, cx + ox + bbox_w, cy + oy + ry], fill=color)


def _paint_rain(image: Image.Image, rng: random.Random, density: int, color=(210, 224, 240)) -> None:
    draw = ImageDraw.Draw(image)
    for _ in range(density):
        x = rng.randint(0, IMAGE_SIZE)
        y = rng.randint(160, _HORIZON_Y)
        length = rng.randint(22, 40)
        draw.line([(x, y), (x - 8, y + length)], fill=color, width=2)
    # Ho'l yo'l/aks — pastki chiziqda yumshoq yorug' chiziqlar.
    for _ in range(6):
        x = rng.randint(60, IMAGE_SIZE - 60)
        w = rng.randint(60, 140)
        draw.line([(x, IMAGE_SIZE - 40), (x + w, IMAGE_SIZE - 40)], fill=(180, 200, 220), width=3)


def _paint_snow(image: Image.Image, rng: random.Random, density: int = 140) -> None:
    draw = ImageDraw.Draw(image)
    for _ in range(density):
        x = rng.randint(0, IMAGE_SIZE)
        y = rng.randint(120, _HORIZON_Y - 20)
        radius = rng.choice([2, 3, 4])
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(255, 255, 255))


def _paint_fog(image: Image.Image, rng: random.Random) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for band in range(6):
        y = 260 + band * 90
        alpha = 70 - band * 4
        draw.rectangle([0, y, IMAGE_SIZE, y + 70], fill=(235, 238, 240, max(20, alpha)))
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"), (0, 0))


def _paint_lightning(image: Image.Image, rng: random.Random) -> None:
    _soft_glow(image, (300, 260), radius=220, color=(220, 225, 255), max_alpha=35)
    draw = ImageDraw.Draw(image)
    x, y = 300, 150
    points = [(x, y)]
    for _ in range(4):
        x += rng.randint(-26, 26)
        y += rng.randint(30, 60)
        points.append((x, y))
    draw.line(points, fill=(235, 238, 255), width=5)


def _paint_wind_leaves(image: Image.Image, rng: random.Random, leaf_color) -> None:
    draw = ImageDraw.Draw(image)
    for _ in range(14):
        x = rng.randint(60, IMAGE_SIZE - 60)
        y = rng.randint(150, _HORIZON_Y - 20)
        size = rng.randint(8, 14)
        draw.ellipse([x, y - size // 2, x + size, y + size // 2], fill=leaf_color)
        draw.line([(x - 18, y + 4), (x, y)], fill=leaf_color, width=1)


def _paint_heat_shimmer(image: Image.Image, rng: random.Random) -> None:
    draw = ImageDraw.Draw(image)
    for i in range(5):
        y = _HORIZON_Y - 30 + i * 8
        draw.line([(0, y), (IMAGE_SIZE, y)], fill=(255, 236, 200, 40), width=2)


def _paint_flowers(image: Image.Image, rng: random.Random) -> None:
    draw = ImageDraw.Draw(image)
    for _ in range(10):
        x = rng.randint(40, IMAGE_SIZE - 40)
        y = rng.randint(_HORIZON_Y + 20, IMAGE_SIZE - 30)
        color = rng.choice([(255, 182, 193), (255, 240, 150), (220, 180, 255)])
        draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=color)


def _paint_falling_leaves(image: Image.Image, rng: random.Random, leaf_color) -> None:
    draw = ImageDraw.Draw(image)
    for _ in range(16):
        x = rng.randint(40, IMAGE_SIZE - 40)
        y = rng.randint(160, _HORIZON_Y - 10)
        size = rng.randint(7, 13)
        draw.ellipse([x, y, x + size, y + size], fill=leaf_color)


def render_background(season: str, category: str, time_of_day: str, variant: int) -> Image.Image:
    """To'liq 1080x1080 fon: osmon + ufq + ob-havoga mos unsurlar.
    Matn keyinroq (``services/saturn_image.py``) shaffof "glass card"
    ustiga qo'yiladi — shu sababli bu yerda matn zonasidan (markaziy
    ~380-900 oralig'idan) qat'iy tashqariga chiqishga harakat qilinadi.
    """
    rng = _seed(season, category, time_of_day, variant)
    is_night = time_of_day == TIME_NIGHT

    if is_night:
        sky_top, sky_bottom, ground = _NIGHT_PALETTES[season]
    else:
        sky_top, sky_bottom, ground, foliage = _MORNING_PALETTES[season]

    # Ob-havo kategoriyasiga qarab osmonni biroz xiralashtirish/
    # to'qlashtirish (yomg'ir/tuman/bulut kunlari yorqin quyoshli
    # osmondan farq qilishi kerak).
    def _dim(rgb, factor):
        return tuple(int(c * factor) for c in rgb)

    dim_factor = 1.0
    if category in ("rain", "heavy_rain", "thunderstorm"):
        dim_factor = 0.72 if not is_night else 0.85
    elif category in ("cloudy", "drizzle", "fog"):
        dim_factor = 0.88

    image = _vertical_gradient(_dim(sky_top, dim_factor), _dim(sky_bottom, dim_factor))

    snowy_ground = category == "snow" or (season == "qish" and category in ("season_default", "clear", "cloudy"))
    ground_color = (240, 244, 248) if (snowy_ground and not is_night) else ground
    _paint_ground(image, ground_color, rng, snowy=snowy_ground)

    dark_shop = is_night or category in ("rain", "heavy_rain", "thunderstorm", "fog")
    _paint_shop_silhouette(image, rng, dark=dark_shop)

    foliage_color = (foliage if not is_night else (30, 60, 40))
    if season == "qish":
        foliage_color = (255, 255, 255) if snowy_ground else foliage_color
    bent = category == "windy"
    _paint_tree_or_bush(image, rng, foliage_color, bent=bent)

    if is_night:
        if category == "clear":
            _paint_moon_and_stars(image, rng)
        elif category in ("cloudy",):
            _paint_clouds(image, rng, count=4, color=(40, 50, 70))
        elif category in ("rain", "drizzle"):
            _paint_clouds(image, rng, count=3, color=(30, 38, 55))
            _paint_rain(image, rng, density=70 if category == "rain" else 30, color=(120, 150, 190))
        elif category == "heavy_rain":
            _paint_clouds(image, rng, count=4, color=(22, 28, 42))
            _paint_rain(image, rng, density=110, color=(120, 150, 190))
        elif category == "thunderstorm":
            _paint_clouds(image, rng, count=4, color=(18, 20, 32))
            _paint_rain(image, rng, density=60, color=(110, 130, 170))
            _paint_lightning(image, rng)
        elif category == "snow":
            _paint_snow(image, rng, density=110)
        elif category == "fog":
            _paint_fog(image, rng)
        elif category == "windy":
            _paint_clouds(image, rng, count=3, color=(35, 45, 65), stretched=True)
        else:  # hot, season_default
            _paint_moon_and_stars(image, rng)
    else:
        if category == "clear":
            _paint_sun(image, rng)
            _paint_clouds(image, rng, count=2, color=(255, 255, 255))
        elif category == "cloudy":
            _paint_clouds(image, rng, count=6, color=(250, 250, 252))
        elif category == "hot":
            _paint_sun(image, rng, center=(860, 170))
            _paint_heat_shimmer(image, rng)
        elif category == "windy":
            _paint_clouds(image, rng, count=4, color=(255, 255, 255), stretched=True)
            _paint_wind_leaves(image, rng, foliage_color)
        elif category == "drizzle":
            _paint_clouds(image, rng, count=5, color=(232, 236, 240))
            _paint_rain(image, rng, density=35)
        elif category == "rain":
            _paint_clouds(image, rng, count=6, color=(214, 220, 228))
            _paint_rain(image, rng, density=80)
        elif category == "heavy_rain":
            _paint_clouds(image, rng, count=7, color=(190, 198, 210))
            _paint_rain(image, rng, density=130)
        elif category == "fog":
            _paint_fog(image, rng)
        elif category == "snow":
            _paint_snow(image, rng, density=130)
        elif category == "thunderstorm":
            _paint_clouds(image, rng, count=6, color=(150, 152, 166))
            _paint_rain(image, rng, density=70)
            _paint_lightning(image, rng)
        else:  # season_default
            if season == "bahor":
                _paint_sun(image, rng, center=(860, 220))
                _paint_flowers(image, rng)
            elif season == "yoz":
                _paint_sun(image, rng)
            elif season == "kuz":
                _paint_falling_leaves(image, rng, foliage_color)
            else:
                _paint_clouds(image, rng, count=3, color=(255, 255, 255))

    return image
