"""Rasmdan (kassa/ombor hisoboti) raqam o'qish uchun abstraksiya.

``config.VISION_EXTRACTION_ENABLED`` ``False`` bo'lsa (standart),
``NullVisionExtractionProvider`` ishlatiladi: har doim "ishonch yetarli
emas" natija qaytaradi, bot esa har doim raqamni qo'lda so'raydi —
hech qachon raqamni o'zi o'ylab topmaydi.

``True`` bo'lsa, ``OpenAIVisionExtractionProvider`` mavjud (bot allaqachon
qabul qiladigan) ``AsyncOpenAI`` klient orqali ishlaydi — yangi secret
yoki alohida AI tizimi YO'Q. ``file_id`` bu yerda Telegram file_id EMAS —
chaqiruvchi (bot qatlami) uni oldindan vision API tushunadigan ``data:``
URI'ga aylantiradi, shunda bu modul Telegramdan butunlay mustaqil
qoladi va protokol imzosi o'zgarmaydi.

Har bir maydon faqat "clear" (``values`` dict'da bor) yoki "unclear"
(``values``da yo'q) bo'ladi — sun'iy foiz/confidence hech qachon
o'ylab topilmaydi (``confident`` faqat "AI chaqiruvi umuman ishladimi"
degan ma'noda, natijaning har bir maydoni bo'yicha EMAS).
"""

import json
import re
from dataclasses import dataclass
from typing import Protocol

from openai import AsyncOpenAI

import config


@dataclass
class ExtractionResult:
    confident: bool
    values: dict[str, str]


class VisionExtractionProvider(Protocol):
    async def extract(self, file_id: str, document_type: str) -> ExtractionResult: ...

    def is_enabled(self) -> bool: ...


class NullVisionExtractionProvider:
    """OCR/vision provider o'chirilgan holatdagi standart implementatsiya."""

    async def extract(self, file_id: str, document_type: str) -> ExtractionResult:
        return ExtractionResult(confident=False, values={})

    def is_enabled(self) -> bool:
        return False


# Kassa smenasi uchun ikkita hujjat turi — har biri o'zining maydonlari
# va promptiga ega (savdo hisoboti / kassa-xarajat daftari).
CASH_SHIFT_SALES_REPORT = "cash_shift_sales_report"
CASH_SHIFT_CASH_REPORT = "cash_shift_cash_report"

_AI_MODEL = "gpt-5-mini"  # repoda allaqachon ishlatilayotgan model (services/deficiency_list_ai.py)

_SALES_REPORT_PROMPT = (
    "Bu — kassir kunlik SAVDO HISOBOTI varag'ining fotosurati (qo'lda "
    "yozilgan). Undan quyidagi maydonlarni o'qi: cash_sales (naqd savdo "
    "summasi), card_sales (karta savdo summasi), other_payments (boshqa "
    "to'lovlar summasi). Faqat quyidagi JSON formatida javob ber, boshqa "
    "hech narsa yozma:\n"
    '{"cash_sales": "<son yoki \\"unclear\\">", '
    '"card_sales": "<son yoki \\"unclear\\">", '
    '"other_payments": "<son yoki \\"unclear\\">"}\n'
    "Yozuv bo'sh, o'qilmaydigan, ikki xil o'qilishi mumkin yoki pul "
    "formati noto'g'ri bo'lsa — o'sha maydon uchun aynan \"unclear\" "
    "yoz. Hech qanday hisob-kitob qilma, faqat qog'ozda yozilganini o'qi."
)

_CASH_REPORT_PROMPT = (
    "Bu — kassir kunlik KASSA/XARAJAT daftari varag'ining fotosurati "
    "(qo'lda yozilgan). Undan quyidagilarni o'qi: actual_cash_balance "
    "(kassadagi haqiqiy naqd pul qoldig'i), expense_lines (varaqdagi har "
    "bir xarajat qatorining summasi, ro'yxat sifatida), written_total "
    "(agar varaqda alohida yozilgan jami xarajat bo'lsa). Faqat quyidagi "
    "JSON formatida javob ber, boshqa hech narsa yozma:\n"
    '{"actual_cash_balance": "<son yoki \\"unclear\\">", '
    '"expense_lines": [<sonlar ro\'yxati>], '
    '"written_total": "<son yoki null>"}\n'
    "Yozuv bo'sh, o'qilmaydigan, ikki xil o'qilishi mumkin yoki pul "
    "formati noto'g'ri bo'lsa — \"actual_cash_balance\" uchun aynan "
    "\"unclear\" yoz. Hech qanday hisob-kitob qilma, faqat qog'ozda "
    "yozilganini o'qi."
)

_PROMPTS = {
    CASH_SHIFT_SALES_REPORT: _SALES_REPORT_PROMPT,
    CASH_SHIFT_CASH_REPORT: _CASH_REPORT_PROMPT,
}

_AMOUNT_RE = re.compile(r"^-?\d+$")


def _clean_amount(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip().replace(" ", "").replace("'", "").replace(",", "")
    if not _AMOUNT_RE.match(cleaned):
        return None
    return cleaned


class OpenAIVisionExtractionProvider:
    """Mavjud ``AsyncOpenAI`` klient orqali qog'ozdagi yozuvni o'qiydi."""

    def __init__(self, client: AsyncOpenAI | None):
        self._client = client

    def is_enabled(self) -> bool:
        return bool(config.VISION_EXTRACTION_ENABLED) and self._client is not None

    async def extract(self, file_id: str, document_type: str) -> ExtractionResult:
        prompt = _PROMPTS.get(document_type)
        if not self.is_enabled() or prompt is None:
            return ExtractionResult(confident=False, values={})

        try:
            response = await self._client.responses.create(
                model=_AI_MODEL,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {"type": "input_image", "image_url": file_id},
                        ],
                    }
                ],
            )
            data = json.loads(response.output_text)
        except Exception as error:  # noqa: BLE001
            print(f"OpenAI xatosi (vision extraction, {document_type}): {error!r}")
            return ExtractionResult(confident=False, values={})

        if not isinstance(data, dict):
            return ExtractionResult(confident=False, values={})

        values: dict[str, str] = {}

        if document_type == CASH_SHIFT_SALES_REPORT:
            for field in ("cash_sales", "card_sales", "other_payments"):
                amount = _clean_amount(data.get(field))
                if amount is not None:
                    values[field] = amount
        else:
            expense_lines_raw = data.get("expense_lines")
            written_total = _clean_amount(data.get("written_total"))
            lines_sum = None
            if isinstance(expense_lines_raw, list) and expense_lines_raw:
                cleaned_lines = [_clean_amount(str(item)) for item in expense_lines_raw]
                if all(item is not None for item in cleaned_lines):
                    lines_sum = sum(int(item) for item in cleaned_lines)

            # Ichki mos kelish tekshiruvi — AI hisoblamaydi, bu shunchaki
            # o'qilgan ikkita raqamni solishtirish (kamomad formulasi
            # EMAS). Mos kelmasa, shu varaqdan o'qilgan qoldiq ham
            # unclear hisoblanadi (PHASE2 #9).
            sums_consistent = (
                lines_sum is None or written_total is None or str(lines_sum) == written_total
            )
            balance = _clean_amount(data.get("actual_cash_balance"))
            if balance is not None and sums_consistent:
                values["actual_cash_balance"] = balance

        return ExtractionResult(confident=True, values=values)


def get_vision_extraction_provider(
    openai_client: AsyncOpenAI | None = None,
) -> VisionExtractionProvider:
    if config.VISION_EXTRACTION_ENABLED and openai_client is not None:
        return OpenAIVisionExtractionProvider(openai_client)
    return NullVisionExtractionProvider()
