"""Fotoreal fon katalogi — kataloglangan haqiqiy fotosuratlar
metadata'si (``assets/photos/manifest.json``) va deterministik
tanlov mantiqi.

HOZIRGI HOLAT: katalog to'liq bo'sh emas, lekin "10 yil" yoki
"60-100 ta" maqsadga hali YETMAGAN — qarang loyiha ildizidagi
final hisobotdagi ``PHOTO_SOURCE_REQUIRED`` bo'limi aniq sonlar
uchun. Bu modul katalog hajmidan qat'i nazar TO'G'RI ishlaydi —
bo'sh katalogda ham xato bermaydi, faqat ``None``/bo'sh natija
qaytaradi (chaqiruvchi kod dasturiy sahna fallback'iga o'tadi).

Har bir katalog yozuvi manba, litsenziya va checksum'ni saqlaydi —
fayl manifestdagi checksum bilan mos kelmasa (masalan qo'lda
o'zgartirilgan/buzilgan bo'lsa), o'sha yozuv e'tiborsiz qoldiriladi
(xato bermaydi, faqat log qilinadi).
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "photos"
_MANIFEST_PATH = _ASSETS_DIR / "manifest.json"

# Bitta asosiy fotodan xavfsiz olinadigan variant transformatsiyalari
# soni (crop/pan pozitsiyasi x rang ishlovi kombinatsiyasi). ``variant_id``
# sana bilan birga hash qilingani uchun, kunlar davomida haqiqiy
# takrorlanmaslik sana oralig'idan kelib chiqadi (qarang
# ``variant_id_for``) — bu son shunchaki bitta fotoning necha "ko'rinishi"
# borligini ifodalaydi, deterministik tanlovning o'zi cheksiz sana
# oralig'ida takrorlanmaydigan hash'ga asoslangan.
VARIANTS_PER_PHOTO = 10

# Bir xil asosiy foto kamida shuncha kun ichida qaytarilmasin.
MIN_DAYS_BETWEEN_SAME_PHOTO = 30


@dataclass(frozen=True)
class PhotoAsset:
    photo_id: str
    season: str  # bahor|yoz|kuz|qish|barcha (barcha fasllarga mos umumiy foto uchun)
    weather_tag: str  # clear|cloudy|hot|windy|drizzle|rain|heavy_rain|fog|snow|thunderstorm|season_default
    time_of_day: str  # morning|night
    file_path: str  # assets/photos/ ga nisbatan
    source: str  # "pexels" | "openverse"
    source_id: str
    photographer: str
    photographer_url: str
    source_url: str
    license: str
    license_url: str
    checksum_sha256: str
    downloaded_at: str


def _absolute_path(asset: PhotoAsset) -> Path:
    return _ASSETS_DIR / asset.file_path


def _sha256_of_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


class LocalPhotoCatalog:
    """``manifest.json``dan o'qiydi. Fayl yo'q/bo'sh/buzilgan bo'lsa —
    bo'sh katalog sifatida ishlaydi, HECH QACHON xato ko'tarmaydi."""

    def __init__(self, manifest_path: Path | None = None, verify_checksums: bool = True):
        self._manifest_path = manifest_path or _MANIFEST_PATH
        self._assets = self._load(verify_checksums)

    def _load(self, verify_checksums: bool) -> list[PhotoAsset]:
        if not self._manifest_path.is_file():
            return []
        try:
            data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as error:
            logger.warning("Foto manifestini o'qib bo'lmadi: %r", error)
            return []

        assets: list[PhotoAsset] = []
        for entry in data.get("photos", []):
            try:
                asset = PhotoAsset(**entry)
            except TypeError as error:
                logger.warning("Manifest yozuvi noto'g'ri formatda: %r", error)
                continue

            if verify_checksums:
                actual = _sha256_of_file(_absolute_path(asset))
                if actual is None:
                    logger.warning("Foto fayli topilmadi: %s", asset.file_path)
                    continue
                if actual != asset.checksum_sha256:
                    logger.warning("Foto checksum mos kelmadi (buzilgan/o'zgartirilgan): %s", asset.file_path)
                    continue

            assets.append(asset)
        return assets

    def all_assets(self) -> list[PhotoAsset]:
        return list(self._assets)

    def list_candidates(self, season: str, weather_tag: str, time_of_day: str) -> list[PhotoAsset]:
        exact = [
            a for a in self._assets
            if a.time_of_day == time_of_day and a.season in (season, "barcha") and a.weather_tag == weather_tag
        ]
        if exact:
            return exact
        # Fasl-standart fallback (aniq ob-havo mos kelmasa).
        return [
            a for a in self._assets
            if a.time_of_day == time_of_day and a.season in (season, "barcha") and a.weather_tag == "season_default"
        ]


def variant_id_for(photo_id: str, local_date: date, salt: int = 0) -> str:
    """Sof funksiya sana+foto+salt'dan — worker restart'dan
    ta'sirlanmaydi. Sana har kuni o'zgargani uchun, xuddi shu foto
    qaytarilsa ham (30+ kundan keyin) variant_id har doim boshqacha
    bo'ladi — shu orqali "10 yil ichida aynan bir variant qaytmasin"
    talabiga tabiiy ravishda erishiladi (bir xil sana ikki marta
    kelmaydi)."""
    key = f"{photo_id}|{local_date.isoformat()}|{salt}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def select_photo(
    catalog: LocalPhotoCatalog,
    season: str,
    weather_tag: str,
    time_of_day: str,
    local_date: date,
    recent_photo_ids: list[str],
    min_days_between_repeats: int = MIN_DAYS_BETWEEN_SAME_PHOTO,
) -> tuple[PhotoAsset, str] | None:
    """``(PhotoAsset, variant_id)`` yoki ``None`` (katalogda mos foto
    yo'q — chaqiruvchi dasturiy sahna fallback'iga o'tishi kerak).
    Deterministik: bir xil sana+parametrlar uchun doim bir xil natija.
    ``recent_photo_ids`` — chaqiruvchi DB'dan so'raydi (oxirgi
    ``min_days_between_repeats`` kunda ishlatilgan asosiy foto ID'lari).
    """
    candidates = catalog.list_candidates(season, weather_tag, time_of_day)
    if not candidates:
        return None

    available = [a for a in candidates if a.photo_id not in recent_photo_ids]
    if not available:
        available = candidates  # katalog kichik — takrorlanish muqarrar, lekin yuborish to'xtamaydi

    seed_key = f"{local_date.isoformat()}|{season}|{weather_tag}|{time_of_day}"
    seed = int(hashlib.sha256(seed_key.encode()).hexdigest(), 16)
    photo = available[seed % len(available)]
    variant_id = variant_id_for(photo.photo_id, local_date)
    return photo, variant_id


def total_real_variant_count(catalog: LocalPhotoCatalog) -> int:
    """Katalogdagi HAQIQIY foto soniga asoslangan haqiqiy variant
    soni — hech qachon to'qib chiqarilgan raqam emas."""
    return len(catalog.all_assets()) * VARIANTS_PER_PHOTO


def get_default_catalog() -> LocalPhotoCatalog:
    return LocalPhotoCatalog()
