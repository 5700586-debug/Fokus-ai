"""Fayl/rasm saqlash abstraksiyasi.

Rasmlar DB'ga BLOB sifatida yozilmaydi — mavjud ``photo_file_id``
patterni davom ettiriladi: haqiqiy fayl Telegram serverida qoladi, DB
faqat ``file_id`` + metadata (owner, category, created_at) saqlaydi
(masalan ``market_observations.photo_reference``,
``vehicle_daily_checks.exterior_photo_ref``).

Retention policy shu yerda konfiguratsiya qilinadi, lekin avtomatik
o'chirish HALI yoqilmagan — faqat ``retention_days()`` orqali qaysi
kategoriya qancha muddat saqlanishi kerakligi e'lon qilinadi.
``None`` = muddat belgilanmagan (masalan muhim servis hujjatlari).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


@dataclass
class FileReference:
    file_id: str
    owner_id: int
    category: str
    created_at: str


class FileStorageProvider(Protocol):
    def register(self, file_id: str, owner_id: int, category: str) -> FileReference: ...

    def retention_days(self, category: str) -> int | None: ...


class TelegramFileStorageProvider:
    _RETENTION_DAYS: dict[str, int] = {
        "vehicle_daily_photo": 90,
        "market_observation_photo": 90,
        "cash_shift_photo": 180,
        "inventory_snapshot_photo": 180,
    }

    def register(self, file_id: str, owner_id: int, category: str) -> FileReference:
        return FileReference(
            file_id=file_id,
            owner_id=owner_id,
            category=category,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def retention_days(self, category: str) -> int | None:
        return self._RETENTION_DAYS.get(category)


def get_file_storage_provider() -> FileStorageProvider:
    return TelegramFileStorageProvider()
