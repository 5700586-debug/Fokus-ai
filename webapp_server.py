"""📱 Baholash ekrani (Telegram Mini App) uchun HTTP yo'llar — mavjud health serverga qo'shiladi (yangi servis yo'q).

GET  /app/baholash        — bitta statik sahifa (inline JS/CSS).
POST /api/baholash/day    — {"initData"} -> faol ish kuni, filiallar, xodimlar holati.
POST /api/baholash/grade  — {"initData", "employee_id", "grade"} -> ``services.grading_webapp.grade``.

Foydalanuvchi faqat imzolangan initData'dan aniqlanadi; CORS sarlavhalari yo'q; javob keshlanmaydi.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from aiohttp import web

from services import grading_webapp

logger = logging.getLogger(__name__)

PAGE_PATH = "/app/baholash"
_PAGE_FILE = Path(__file__).resolve().parent / "assets" / "webapp" / "baholash.html"
_MAX_BODY = 16 * 1024
_NO_STORE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def page_url() -> str | None:
    """Mini App manzili. Render ``RENDER_EXTERNAL_URL``ni o'zi beradi; boshqa joyda ``WEBAPP_BASE_URL``. Faqat https."""
    base = (os.getenv("WEBAPP_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if not base.startswith("https://"):
        return None
    return base + PAGE_PATH


def _json(data: dict, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, headers=_NO_STORE)


async def _read_body(request: web.Request) -> dict:
    if request.content_length is not None and request.content_length > _MAX_BODY:
        raise grading_webapp.WebAppError(413, "So'rov juda katta.")
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001 - noto'g'ri JSON
        raise grading_webapp.WebAppError(400, "Noto'g'ri so'rov.") from None
    if not isinstance(data, dict):
        raise grading_webapp.WebAppError(400, "Noto'g'ri so'rov.")
    return data


def add_routes(app: web.Application, *, bot, bot_token: str, fsm_storage=None) -> None:
    async def page(request: web.Request) -> web.Response:
        return web.Response(
            text=_PAGE_FILE.read_text(encoding="utf-8"), content_type="text/html", charset="utf-8", headers=_NO_STORE
        )

    async def _handle(request: web.Request, action) -> web.Response:
        try:
            body = await _read_body(request)
            user_id = grading_webapp.authenticate(str(body.get("initData") or ""), bot_token)
            grading_webapp.check_rate(user_id)
            return _json(await action(user_id, body))
        except grading_webapp.WebAppError as error:
            return _json({"ok": False, "error": error.message}, error.status)
        except Exception as error:  # noqa: BLE001 - ichki xato tafsiloti klientga chiqmaydi
            logger.exception("Baholash ekrani xatosi: %s", type(error).__name__)
            return _json({"ok": False, "error": "Server xatosi — qayta urinib ko'ring."}, 500)

    async def day(request: web.Request) -> web.Response:
        async def action(user_id, body):
            return {"ok": True, **grading_webapp.day_payload(user_id)}

        return await _handle(request, action)

    async def grade(request: web.Request) -> web.Response:
        async def action(user_id, body):
            return await grading_webapp.grade(bot, fsm_storage, user_id, body.get("employee_id"), body.get("grade"))

        return await _handle(request, action)

    app.router.add_get(PAGE_PATH, page)
    app.router.add_post("/api/baholash/day", day)
    app.router.add_post("/api/baholash/grade", grade)
