"""Nomzodning ovozli javobini matnga aylantirish.

Faqat OVOZ MAZMUNI (nima deyilgani) matnga o'giriladi — aksent,
ovoz ohangi, yosh/jins taxmini, hissiy holat yoki "yolg'on gapiryapti"
kabi xulosa HECH QACHON chiqarilmaydi (bunday tahlil so'ralmaydi ham,
imkoni ham yo'q — faqat matn qaytariladi).

Transkripsiya xizmati ishlamasa yoki ``AsyncOpenAI`` mijozi mavjud
bo'lmasa, ``None`` qaytariladi — chaqiruvchi kod (``recruiting_bot.py``)
bunda nomzoddan yozma javob so'rashi kerak, ariza HECH QACHON
to'xtamaydi.
"""

import io
import logging

from aiogram import Bot
from aiogram.types import Voice
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_TRANSCRIPTION_MODEL = "whisper-1"


async def transcribe_voice(bot: Bot, voice: Voice, client: AsyncOpenAI | None) -> str | None:
    """Ovozli xabarni yuklab olib, transkripsiya qiladi. Har qanday
    xato (tarmoq, fayl, AI) ``None`` qaytaradi — hech qachon exception
    ko'tarmaydi, chaqiruvchi kod fallback (matn so'rash) qo'llaydi."""
    if client is None:
        return None

    try:
        file_info = await bot.get_file(voice.file_id)
        buffer = io.BytesIO()
        await bot.download_file(file_info.file_path, destination=buffer)
        buffer.seek(0)
        buffer.name = "voice.ogg"

        response = await client.audio.transcriptions.create(
            model=_TRANSCRIPTION_MODEL, file=buffer
        )
        text = (getattr(response, "text", None) or "").strip()
        return text or None
    except Exception as error:  # noqa: BLE001 - transkripsiya xatosi arizani to'xtatmasin
        logger.warning("Ovozni matnga o'girishda xato: %r", error)
        return None
