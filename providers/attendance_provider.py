"""Davomat event manbai uchun abstraksiya.

Hozircha Face ID yoki boshqa real manba ulanmagan — bu interfeys
kelajakda ular ulanganda ishlatiladi. Bugun hech qanday implementatsiya
yozilmaydi (faqat ``schema/attendance.py`` va
``repositories/attendance.py`` tayyor).
"""

from typing import Protocol


class AttendanceEventProvider(Protocol):
    async def record_event(self, employee_id: int, event_type: str, source: str) -> None: ...

    def is_enabled(self) -> bool: ...
