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

_CASH_FIELDS = ("cash_sales", "card_sales", "other_payments", "actual_cash_balance")

_SALES_REPORT_PROMPT = (
    "Bu — kassir kunlik SAVDO HISOBOTI varag'ining fotosurati (qo'lda yozilgan). "
    "Rasmda aniq ko'ringan bo'lsa quyidagi maydonlarning BARCHASINI o'qi: "
    "cash_sales (naqd/nalichka savdo), card_sales (karta/terminal/plastik savdo), "
    "other_payments (boshqa to'lovlar) va actual_cash_balance (kassadagi pul, "
    "qoldiq yoki oxirgi pul). actual_cash_balance faqat qoldiq ekanligi aniq "
    "yozilgan bo'lsa olinadi; jami savdoni unga tenglashtirma. Faqat quyidagi "
    "JSON formatida javob ber, boshqa hech narsa yozma:\n"
    '{"cash_sales": "<son yoki \\"unclear\\">", '
    '"card_sales": "<son yoki \\"unclear\\">", '
    '"other_payments": "<son yoki \\"unclear\\">", '
    '"actual_cash_balance": "<son yoki \\"unclear\\">"}\n'
    "Yozuv bo'sh, o'qilmaydigan yoki ikki xil o'qilishi mumkin bo'lsa o'sha "
    "maydon uchun aynan \"unclear\" yoz. Rasmda yo'q qiymatni o'ylab topma "
    "va hisob-kitob qilma."
)

_CASH_REPORT_PROMPT = (
    "Bu — kassir kunlik KASSA/XARAJAT daftari varag'ining fotosurati "
    "(qo'lda yozilgan). Rasmda aniq ko'ringan bo'lsa quyidagi maydonlarning "
    "BARCHASINI o'qi: cash_sales (naqd/nalichka savdo), card_sales "
    "(karta/terminal/plastik savdo), other_payments (boshqa to'lovlar), "
    "actual_cash_balance (kassadagi pul/qoldiq/oxirgi pul), expense_lines "
    "(xarajat/rasxod qatorlaridagi summalar) va written_total (FAQAT \"jami "
    "xarajat\" yoki \"jami rasxod\" deb aniq yozilgan summa; boshqa jami "
    "savdo yoki mahsulot jami emas). Faqat quyidagi JSON formatida javob ber, "
    "boshqa hech narsa yozma:\n"
    '{"cash_sales": "<son yoki \\"unclear\\">", '
    '"card_sales": "<son yoki \\"unclear\\">", '
    '"other_payments": "<son yoki \\"unclear\\">", '
    '"actual_cash_balance": "<son yoki \\"unclear\\">", '
    '"expense_lines": [<sonlar ro\'yxati>], '
    '"written_total": "<son yoki null>"}\n'
    "Yozuv bo'sh, o'qilmaydigan yoki ikki xil o'qilishi mumkin bo'lsa o'sha "
    "maydon uchun aynan \"unclear\" yoz. Rasmda yo'q qiymatni o'ylab topma "
    "va hisob-kitob qilma."
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
        for field in _CASH_FIELDS:
            amount = _clean_amount(data.get(field))
            if amount is not None:
                values[field] = amount

        # Xarajat qatorlari faqat o'zaro tekshiriladi. Ularning tafovuti
        # boshqa, mustaqil o'qilgan summalarni (ayniqsa kassa qoldig'ini)
        # bekor qilmaydi.
        expense_check = "not_applicable"
        if document_type == CASH_SHIFT_CASH_REPORT:
            expense_check = "not_available"
            expense_lines_raw = data.get("expense_lines")
            written_total = _clean_amount(data.get("written_total"))
            if isinstance(expense_lines_raw, list) and expense_lines_raw:
                cleaned_lines = [_clean_amount(str(item)) for item in expense_lines_raw]
                if all(item is not None for item in cleaned_lines):
                    lines_sum = sum(int(item) for item in cleaned_lines)
                    if written_total is not None:
                        expense_check = (
                            "clear" if lines_sum == int(written_total) else "conflict"
                        )
                    else:
                        expense_check = "lines_only"

        field_status = " ".join(
            f"{field}={'clear' if field in values else 'unclear'}"
            for field in _CASH_FIELDS
        )
        print(
            f"VISION_CASH_READ document={document_type} {field_status} "
            f"expense_check={expense_check}"
        )

        return ExtractionResult(confident=True, values=values)


def get_vision_extraction_provider(
    openai_client: AsyncOpenAI | None = None,
) -> VisionExtractionProvider:
    if config.VISION_EXTRACTION_ENABLED and openai_client is not None:
        return OpenAIVisionExtractionProvider(openai_client)
    return NullVisionExtractionProvider()
