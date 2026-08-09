"""SMS yuborish uchun abstraksiya.

Real SMS provider hali tanlanmagan. Shuning uchun credential
hardcode qilinmaydi — ``config.py`` dagi ``SMS_PROVIDER_ENABLED`` flag
yo'q yoki ``False`` bo'lsa, ``NullSMSProvider`` ishlatiladi: hech narsa
yubormaydi, xato ko'tarmaydi, botni yiqitmaydi.

Real provider ulanganda shu ``SMSProvider`` protokoliga mos yangi klass
(masalan ``EskizSMSProvider``) qo'shiladi va ``get_sms_provider()``
uni qaytaradi.
"""

from typing import Protocol


class SMSProvider(Protocol):
    async def send_sms(self, phone: str, text: str) -> bool:
        """Muvaffaqiyatli yuborilsa ``True``, aks holda ``False``."""
        ...

    def is_enabled(self) -> bool: ...


class NullSMSProvider:
    """SMS provider ulanmagan holatdagi standart implementatsiya."""

    async def send_sms(self, phone: str, text: str) -> bool:
        return False

    def is_enabled(self) -> bool:
        return False


def get_sms_provider() -> SMSProvider:
    return NullSMSProvider()
