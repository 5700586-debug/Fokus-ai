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
from dataclasses import dataclass, field
from typing import Protocol

from openai import AsyncOpenAI

import config


@dataclass
class ExtractionResult:
    confident: bool
    values: dict[str, str]
    # Kassa/xarajat daftaridan o'qilgan har bir xarajat qatori:
    # {"raw_name", "normalized_name", "amount": int}. Hisob-kitobda faqat amount.
    expense_items: list[dict] = field(default_factory=list)
    written_expense_total: str | None = None
    expense_total_mismatch: bool = False
    # Qatorlar summasi (faqat amount); solishtirib bo'lmasa (yaroqsiz qator/yo'q) None.
    expense_items_sum: int | None = None


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
    "(qo'lda yozilgan). Varaqda \"SOTIB OLISH / XARAJATLAR\" bo'limi bor (25 tagacha qator): "
    "har qatorda mahsulot/xarajat nomi va summa. Undan quyidagilarni o'qi: "
    "cash_sales (varaqda \"savdo\" deb aniq yozilgan summa; bo'lmasa yoki naqd savdo ekani "
    "noaniq bo'lsa \"unclear\"), actual_cash_balance (kassadagi haqiqiy naqd pul qoldig'i), "
    "expense_items (har bir xarajat qatori: raw_name — kassir yozgan asl nom AYNAN qog'ozdagidek; "
    "normalized_name — tushunganing standart nom (imlo xatosini to'g'rila, masalan \"abinon\" -> "
    "\"Obinon\"), ishonchsiz bo'lsa null; amount — shu qatorning summasi), "
    "written_expense_total (varaqda alohida yozilgan \"Jami xarajat\" bo'lsa, aks holda null). "
    "Faqat quyidagi JSON formatida javob ber, boshqa hech narsa yozma:\n"
    '{"cash_sales": "<son yoki \\"unclear\\">", '
    '"actual_cash_balance": "<son yoki \\"unclear\\">", '
    '"expense_items": [{"raw_name": "<matn>", "normalized_name": "<matn yoki null>", "amount": "<son>"}], '
    '"written_expense_total": "<son yoki null>"}\n'
    "Yozuv bo'sh, o'qilmaydigan, ikki xil o'qilishi mumkin yoki pul "
    "formati noto'g'ri bo'lsa — \"actual_cash_balance\" uchun aynan "
    "\"unclear\" yoz. Nomni o'qiy olmasang ham qatorni tashlama: raw_name'ga ko'ringanini yoz. "
    "Hech qanday hisob-kitob qilma va hech narsani o'zing to'qima, faqat qog'ozda yozilganini o'qi."
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


_MAX_EXPENSE_ITEMS = 50
_MAX_NAME_LENGTH = 80


def _clean_name(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    cleaned = " ".join(raw.split())[:_MAX_NAME_LENGTH]
    return cleaned or None


def _parse_expense_items(raw_items) -> tuple[list[dict], bool]:
    """``expense_items`` -> ([{raw_name, normalized_name, amount:int}], has_invalid).
    Summasi yaroqsiz (musbat butun son emas) qatorlar saqlanmaydi va ``has_invalid``
    belgilanadi (jami solishtirib bo'lmaydi). Nom noaniq bo'lsa ham qator tashlanmaydi:
    ``raw_name`` bo'sh bo'lsa ``normalized_name``, u ham bo'lmasa "Noma'lum"."""
    if not isinstance(raw_items, list):
        return [], False

    items: list[dict] = []
    has_invalid = False
    for entry in raw_items[:_MAX_EXPENSE_ITEMS]:
        if not isinstance(entry, dict):
            has_invalid = True
            continue
        amount_text = _clean_amount(str(entry.get("amount")) if entry.get("amount") is not None else None)
        if amount_text is None or int(amount_text) <= 0:
            has_invalid = True
            continue
        raw_name = _clean_name(entry.get("raw_name"))
        normalized = _clean_name(entry.get("normalized_name"))
        raw_name = raw_name or normalized or "Noma'lum"
        items.append({
            "raw_name": raw_name, "normalized_name": normalized or raw_name, "amount": int(amount_text),
        })
    if len(raw_items) > _MAX_EXPENSE_ITEMS:
        has_invalid = True
    return items, has_invalid


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
            items, has_invalid = _parse_expense_items(data.get("expense_items"))
            written_total = _clean_amount(data.get("written_expense_total"))
            if written_total is None:
                written_total = _clean_amount(data.get("written_total"))

            lines_sum = None
            if items and not has_invalid:
                lines_sum = sum(item["amount"] for item in items)
            elif not items and isinstance(data.get("expense_lines"), list) and data["expense_lines"]:
                # Eski format (faqat summalar): nomlarsiz, faqat jami tekshiruvi uchun.
                cleaned_lines = [_clean_amount(str(item)) for item in data["expense_lines"]]
                if all(item is not None for item in cleaned_lines):
                    lines_sum = sum(int(item) for item in cleaned_lines)

            # Ichki mos kelish tekshiruvi — AI hisoblamaydi, bu shunchaki o'qilgan
            # qatorlar summasini (FAQAT amount) yozilgan jami bilan solishtirish
            # (kamomad formulasi EMAS). Mos kelmasa, shu varaqdan o'qilgan qoldiq
            # ham unclear hisoblanadi (PHASE2 #9) — nom xato o'qilsa ham jami buzilmaydi.
            mismatch = lines_sum is not None and written_total is not None and str(lines_sum) != written_total
            cash_sales = _clean_amount(data.get("cash_sales"))
            if cash_sales is not None:
                values["cash_sales"] = cash_sales
            balance = _clean_amount(data.get("actual_cash_balance"))
            if balance is not None and not mismatch:
                values["actual_cash_balance"] = balance

            return ExtractionResult(
                confident=True, values=values, expense_items=items,
                written_expense_total=written_total, expense_total_mismatch=mismatch,
                expense_items_sum=lines_sum,
            )

        return ExtractionResult(confident=True, values=values)


def get_vision_extraction_provider(
    openai_client: AsyncOpenAI | None = None,
) -> VisionExtractionProvider:
    if config.VISION_EXTRACTION_ENABLED and openai_client is not None:
        return OpenAIVisionExtractionProvider(openai_client)
    return NullVisionExtractionProvider()
