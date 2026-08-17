"""Haqiqiy fotosuratga asoslangan Saturn fon kompozitsiyasi.

Kataloglangan asl foto (``services/photo_catalog.py``) ustiga
deterministik crop/pan va yengil yorug'lik/rang ishlovi qo'llanadi.
Ob-havo effektlari (yomg'ir, qor, tuman, chaqmoq, shamol) FAQAT foto
o'zi allaqachon shu ob-havoni ko'rsatmasa qo'shiladi (``apply_weather_overlay``)
— ``services/saturn_scene.py``dagi DASTURIY chizish funksiyalari qayta
ishlatiladi, chunki ular istalgan fon (vektor yoki foto) ustida bir
xil ishlaydi.
"""

import hashlib
import random

from PIL import Image, ImageEnhance

from services import photo_catalog, saturn_scene

IMAGE_SIZE = saturn_scene.IMAGE_SIZE


def _seed(photo_id: str, variant_id: str) -> random.Random:
    key = f"{photo_id}|{variant_id}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return random.Random(int(digest, 16))


def _deterministic_square_crop(photo: Image.Image, rng: random.Random) -> Image.Image:
    """Fotoni deterministik (lekin variant bo'yicha xilma-xil) tarzda
    kvadrat qilib kesadi — original nisbatga qarab yon yoki tepa-past
    joylashuv tasodifiy (lekin seed'ga bog'liq) tanlanadi."""
    width, height = photo.size
    side = min(width, height)
    max_x = width - side
    max_y = height - side
    offset_x = rng.randint(0, max_x) if max_x > 0 else 0
    offset_y = rng.randint(0, max_y) if max_y > 0 else 0
    return photo.crop((offset_x, offset_y, offset_x + side, offset_y + side))


def _apply_grade(image: Image.Image, time_of_day: str, rng: random.Random) -> Image.Image:
    brightness = rng.uniform(0.95, 1.05)
    contrast = rng.uniform(0.97, 1.07)
    saturation = rng.uniform(0.98, 1.08)
    image = ImageEnhance.Brightness(image).enhance(brightness)
    image = ImageEnhance.Contrast(image).enhance(contrast)
    image = ImageEnhance.Color(image).enhance(saturation)
    if time_of_day == saturn_scene.TIME_NIGHT:
        image = ImageEnhance.Brightness(image).enhance(0.94)
    return image


def _apply_weather_overlay(image: Image.Image, weather_category: str, rng: random.Random) -> None:
    """Faqat baza foto o'zi ko'rsatmagan ob-havoni yengil ravishda
    "eslatib qo'yish" uchun — kuchli/haddan tashqari effekt emas."""
    if weather_category in ("rain", "drizzle"):
        density = 30 if weather_category == "drizzle" else 55
        saturn_scene._paint_rain(image, rng, density=density)
    elif weather_category == "heavy_rain":
        saturn_scene._paint_rain(image, rng, density=90)
    elif weather_category == "snow":
        saturn_scene._paint_snow(image, rng, density=80)
    elif weather_category == "fog":
        saturn_scene._paint_fog(image, rng)
    elif weather_category == "thunderstorm":
        saturn_scene._paint_lightning(image, rng)
    elif weather_category == "windy":
        saturn_scene._paint_wind_leaves(image, rng, (225, 222, 195))
    # clear/cloudy/hot/season_default — bazaviy foto allaqachon
    # yetarli, qo'shimcha effekt shart emas.


def render_photo_background(
    asset: photo_catalog.PhotoAsset,
    weather_category: str,
    time_of_day: str,
    variant_id: str,
) -> Image.Image:
    rng = _seed(asset.photo_id, variant_id)
    photo_path = photo_catalog._ASSETS_DIR / asset.file_path
    photo = Image.open(photo_path).convert("RGB")

    cropped = _deterministic_square_crop(photo, rng)
    resized = cropped.resize((IMAGE_SIZE, IMAGE_SIZE), Image.LANCZOS)
    graded = _apply_grade(resized, time_of_day, rng)

    is_exact_weather_match = asset.weather_tag == weather_category
    if not is_exact_weather_match:
        _apply_weather_overlay(graded, weather_category, rng)

    return graded
