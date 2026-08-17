"""Pexels API (https://www.pexels.com/api/documentation/) orqali
haqiqiy, yuqori sifatli tabiat/ob-havo fotosuratlarini qidirish.

``PEXELS_API_KEY`` muhit o'zgaruvchisi ORQALIGINA ishlaydi — kodga,
logga yoki testga hech qachon yozilmaydi. Kalit yo'q bo'lsa
``PexelsProvider.is_enabled()`` ``False`` qaytaradi va qidiruv
funksiyasi darhol bo'sh ro'yxat bilan qaytadi — bot yoki curation
skripti xato bilan TO'XTAMAYDI, faqat bu manba orqali hech narsa
topilmaydi.

Pexels litsenziyasi (https://www.pexels.com/license/) tijoriy
foydalanishga ruxsat beradi, atribut majburiy emas — lekin loyiha
qoidasiga ko'ra har bir foto uchun fotograf va manba havolasi baribir
manifestda saqlanadi va Telegram caption'da qisqa kredit ko'rsatiladi.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.pexels.com/v1"
_REQUEST_TIMEOUT_SECONDS = 8.0


@dataclass
class PexelsPhoto:
    photo_id: str
    photographer: str
    photographer_url: str
    photo_page_url: str
    src_large: str
    src_original: str
    width: int
    height: int


class PexelsProvider:
    def __init__(self, api_key: str, timeout_seconds: float = _REQUEST_TIMEOUT_SECONDS):
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def is_enabled(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: str, per_page: int = 10) -> list[PexelsPhoto]:
        """Kalit bo'lmasa yoki so'rov muvaffaqiyatsiz bo'lsa bo'sh
        ro'yxat qaytaradi — hech qachon xato ko'tarmaydi."""
        if not self._api_key:
            return []

        import aiohttp

        headers = {"Authorization": self._api_key}
        params = {"query": query, "per_page": per_page, "orientation": "square"}
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(f"{_BASE_URL}/search", params=params) as response:
                    if response.status != 200:
                        logger.warning("Pexels HTTP %s (query=%r)", response.status, query)
                        return []
                    data = await response.json()
        except Exception as error:  # noqa: BLE001 - tarmoq xatosi curation/botni to'xtatmasin
            logger.warning("Pexels so'rovida xato (query=%r): %r", query, error)
            return []

        photos = data.get("photos") if isinstance(data, dict) else None
        if not photos:
            return []

        results = []
        for photo in photos:
            try:
                results.append(
                    PexelsPhoto(
                        photo_id=str(photo["id"]),
                        photographer=photo.get("photographer", "Noma'lum"),
                        photographer_url=photo.get("photographer_url", ""),
                        photo_page_url=photo.get("url", ""),
                        src_large=photo["src"]["large2x"],
                        src_original=photo["src"]["original"],
                        width=photo.get("width", 0),
                        height=photo.get("height", 0),
                    )
                )
            except (KeyError, TypeError):
                continue
        return results


def get_pexels_provider() -> PexelsProvider:
    from config import PEXELS_API_KEY

    return PexelsProvider(api_key=PEXELS_API_KEY or "")
