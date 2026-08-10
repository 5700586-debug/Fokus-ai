"""Rasmdan (kassa/ombor hisoboti) raqam o'qish uchun abstraksiya.

Real OCR/vision provider hali ulanmagan. ``config.py`` dagi
``VISION_EXTRACTION_ENABLED`` flag yo'q yoki ``False`` bo'lsa,
``NullVisionExtractionProvider`` ishlatiladi: har doim "ishonch yetarli
emas" natija qaytaradi, bot esa har doim raqamni qo'lda so'raydi —
hech qachon raqamni o'zi o'ylab topmaydi.

Real provider ulanganda shu ``VisionExtractionProvider`` protokoliga
mos yangi klass qo'shiladi va ``get_vision_extraction_provider()`` uni
qaytaradi; qolgan chaqiruvchi kod (bot flow) o'zgarishsiz qoladi —
extraction faqat qo'lda kiritishdan oldingi ixtiyoriy pre-fill bosqichi
bo'lib qo'shiladi.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ExtractionResult:
    confident: bool
    values: dict[str, str]


class VisionExtractionProvider(Protocol):
    async def extract(self, file_id: str, document_type: str) -> ExtractionResult: ...

    def is_enabled(self) -> bool: ...


class NullVisionExtractionProvider:
    """OCR/vision provider ulanmagan holatdagi standart implementatsiya."""

    async def extract(self, file_id: str, document_type: str) -> ExtractionResult:
        return ExtractionResult(confident=False, values={})

    def is_enabled(self) -> bool:
        return False


def get_vision_extraction_provider() -> VisionExtractionProvider:
    return NullVisionExtractionProvider()
