"""📱 Baholash ekrani (Telegram Mini App) uchun HTTP yo'llar — mavjud health serverga qo'shiladi (yangi servis yo'q).

GET  /app/baholash        — bitta statik sahifa (inline JS/CSS).
POST /api/baholash/day    — {"initData"} -> faol ish kuni, filiallar, xodimlar holati.
POST /api/baholash/grade  — {"initData", "employee_id", "grade"} -> ``services.grading_webapp.grade``.
POST /api/baholash/time   — {"initData", "employee_id", "arrival", "departure", "expected_version"} -> ``save_time``.
GET  /app/grafik          — 📅 Grafik ekrani (nazoratchi — hamma filial; filial rahbari — o'z filiali).
POST /api/grafik/week     — {"initData", "week_start"} -> ``services.schedule_webapp.week_payload``.
POST /api/grafik/save     — {"initData", "changes": [...], "reason"} -> bitta tranzaksiya; xodimga bitta xabar.
POST /api/grafik/history  — {"initData", "employee_id", "date"} -> katak tarixi.

Foydalanuvchi faqat imzolangan initData'dan aniqlanadi; CORS sarlavhalari yo'q; javob keshlanmaydi.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from aiohttp import web

from services import grading_webapp, schedule_webapp

logger = logging.getLogger(__name__)

PAGE_PATH = "/app/baholash"
GRAFIK_PATH = "/app/grafik"
_PAGE_FILE = Path(__file__).resolve().parent / "assets" / "webapp" / "baholash.html"
_GRAFIK_FILE = Path(__file__).resolve().parent / "assets" / "webapp" / "grafik.html"
_MAX_BODY = 16 * 1024
_NO_STORE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def page_url(path: str = PAGE_PATH) -> str | None:
    """Mini App manzili. Render ``RENDER_EXTERNAL_URL``ni o'zi beradi; boshqa joyda ``WEBAPP_BASE_URL``. Faqat https."""
    base = (os.getenv("WEBAPP_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if not base.startswith("https://"):
        return None
    return base + path


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
    def _page(file: Path):
        async def page(request: web.Request) -> web.Response:
            return web.Response(
                text=file.read_text(encoding="utf-8"), content_type="text/html", charset="utf-8", headers=_NO_STORE
            )

        return page

    async def _handle(request: web.Request, action, allowed=None) -> web.Response:
        try:
            body = await _read_body(request)
            user_id = grading_webapp.authenticate(str(body.get("initData") or ""), bot_token, allowed=allowed)
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

    async def save_time(request: web.Request) -> web.Response:
        async def action(user_id, body):
            return grading_webapp.save_time(user_id, body.get("employee_id"), body.get("arrival"), body.get("departure"),
                                            body.get("expected_version"))

        return await _handle(request, action)

    async def grafik_week(request: web.Request) -> web.Response:
        async def action(user_id, body):
            return {"ok": True, **schedule_webapp.week_payload(user_id, body.get("week_start"))}

        return await _handle(request, action, schedule_webapp.can_open)

    async def grafik_save(request: web.Request) -> web.Response:
        async def action(user_id, body):
            result = schedule_webapp.save(user_id, body.get("changes"), body.get("reason"))
            notify = result.pop("notify")
            for employee_id, lines in notify.items():  # saqlangandan KEYIN; xabar ketmasa grafik baribir saqlangan
                try:
                    await bot.send_message(employee_id, schedule_webapp.notify_text(lines))
                except Exception:  # noqa: BLE001 - xodim botni bloklagan bo'lishi mumkin
                    logger.warning("Grafik xabari yuborilmadi: %s", employee_id)
            result["notified"] = len(notify)
            return result

        return await _handle(request, action, schedule_webapp.can_open)

    async def grafik_history(request: web.Request) -> web.Response:
        async def action(user_id, body):
            return schedule_webapp.history(user_id, body.get("employee_id"), body.get("date"))

        return await _handle(request, action, schedule_webapp.can_open)

    app.router.add_get(PAGE_PATH, _page(_PAGE_FILE))
    app.router.add_get(GRAFIK_PATH, _page(_GRAFIK_FILE))
    app.router.add_post("/api/grafik/week", grafik_week)
    app.router.add_post("/api/grafik/save", grafik_save)
    app.router.add_post("/api/grafik/history", grafik_history)
    app.router.add_post("/api/baholash/day", day)
    app.router.add_post("/api/baholash/grade", grade)
    app.router.add_post("/api/baholash/time", save_time)
