"""Kunlik savdo ma'lumotlari (reja/haqiqiy/cheklar soni) uchun
abstraksiya.

Loyihada hali hech qanday POS/kassa tizimi savdo raqamlarini
markazlashgan holda yozib bormaydi (``docs/FEATURE_STATUS.md``:
"o'rtacha chek" hisoblash — mavjud emas). Kassa smenasi (``cash_shift``)
faqat naqd pul solishtirish/hisobot uchun, u haqiqiy savdo aylanmasi
emas — shuning uchun bu yerda taxmin qilinmaydi.

``NullSalesDataProvider`` HECH QACHON soxta/taxminiy raqam yaratmaydi —
har bir maydon uchun alohida ``None`` qaytarishi mumkin. Chaqiruvchi kod
(``services/saturn_group.py``dagi dashboard) ``None`` bo'lgan har bir
maydonni "Ma'lumot kelmadi" deb ko'rsatadi, hech qachon 0 yoki boshqa
o'ylab topilgan qiymat bilan to'ldirmaydi.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class DailySales:
    plan_amount: float | None = None
    actual_amount: float | None = None
    receipt_count: int | None = None
    yesterday_actual_amount: float | None = None


class SalesDataProvider(Protocol):
    async def get_daily_sales(self, date_str: str) -> DailySales:
        """Har doim ``DailySales`` qaytaradi — har bir maydon alohida
        ``None`` bo'lishi mumkin, lekin obyektning o'zi hech qachon
        emas (chaqiruvchi kod har safar maydonlarni alohida tekshiradi)."""
        ...

    def is_enabled(self) -> bool: ...


class NullSalesDataProvider:
    async def get_daily_sales(self, date_str: str) -> DailySales:
        return DailySales()

    def is_enabled(self) -> bool:
        return False


def get_sales_data_provider() -> SalesDataProvider:
    return NullSalesDataProvider()
