"""Openverse (https://openverse.org/) orqali kalitsiz, faqat CC0/Public
Domain Mark litsenziyali haqiqiy fotosuratlarni qidirish.

Bu provider hech qanday API kalit talab qilmaydi (anonim so'rovlar
kunlik/daqiqalik chegara bilan ruxsat etilgan). Faqat ``license=cc0,pdm``
filtri bilan so'raladi — lekin Openverse metadata'siga ko'r-ko'rona
ishonilmaydi: har bir tanlangan surat litsenziyasi curation vaqtida
asl manba sahifasidan (``foreign_landing_url``) QO'LDA tasdiqlanishi
kerak (qarang ``assets/photos/LICENSE_MANIFEST.md``dagi jarayon
tavsifi) — bu provider faqat NOMZODLARNI topadi, avtomatik ravishda
"tasdiqlangan" deb belgilamaydi.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.openverse.org/v1/images/"
_REQUEST_TIMEOUT_SECONDS = 10.0
_ALLOWED_LICENSES = {"cc0", "pdm"}


@dataclass
class OpenversePhoto:
    item_id: str
    title: str
    creator: str
    creator_url: str
    foreign_landing_url: str
    image_url: str
    license: str
    license_version: str
    license_url: str
    source: str
    width: int
    height: int


class OpenverseProvider:
    def __init__(self, timeout_seconds: float = _REQUEST_TIMEOUT_SECONDS):
        self._timeout_seconds = timeout_seconds

    def is_enabled(self) -> bool:
        return True  # kalitsiz, doim mavjud

    async def search(self, query: str, per_page: int = 20) -> list[OpenversePhoto]:
        """So'rov muvaffaqiyatsiz bo'lsa bo'sh ro'yxat qaytaradi —
        hech qachon xato ko'tarmaydi. Faqat ``category=photograph`` va
        CC0/PDM litsenziyali natijalar so'raladi."""
        import aiohttp

        params = {
            "q": query,
            "license": "cc0,pdm",
            "category": "photograph",
            "page_size": per_page,
        }
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(_BASE_URL, params=params) as response:
                    if response.status != 200:
                        logger.warning("Openverse HTTP %s (query=%r)", response.status, query)
                        return []
                    data = await response.json()
        except Exception as error:  # noqa: BLE001 - tarmoq xatosi curation/botni to'xtatmasin
            logger.warning("Openverse so'rovida xato (query=%r): %r", query, error)
            return []

        items = data.get("results") if isinstance(data, dict) else None
        if not items:
            return []

        results = []
        for item in items:
            license_key = (item.get("license") or "").lower()
            if license_key not in _ALLOWED_LICENSES:
                continue
            try:
                results.append(
                    OpenversePhoto(
                        item_id=item["id"],
                        title=item.get("title") or "",
                        creator=item.get("creator") or "Noma'lum",
                        creator_url=item.get("creator_url") or "",
                        foreign_landing_url=item["foreign_landing_url"],
                        image_url=item["url"],
                        license=license_key,
                        license_version=item.get("license_version") or "",
                        license_url=item.get("license_url") or "",
                        source=item.get("source") or item.get("provider") or "openverse",
                        width=item.get("width") or 0,
                        height=item.get("height") or 0,
                    )
                )
            except (KeyError, TypeError):
                continue
        return results


def get_openverse_provider() -> OpenverseProvider:
    return OpenverseProvider()
