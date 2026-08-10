"""Render "Web Service" turi uchun minimal HTTP health-check server.

Bu bot Telegram'ga long-polling orqali ulanadi — hech qachon HTTP
so'rov qabul qilmaydi. Lekin Render Free plan faqat "Web Service"
turini beradi (Background Worker pullik), va Web Service ``$PORT``ga
bog'lanishni kutadi — aks holda deploy belgilangan vaqtda (~15 daqiqa)
"Timed out" bo'lib qoladi, garchi bot o'zi to'liq ishlab tursa ham.

Shuning uchun polling bilan bir vaqtda, bitta ``GET /`` so'roviga
``200 OK`` qaytaradigan ahamiyatsiz server ishga tushiriladi.
``aiohttp`` yangi dependency emas — u ``aiogram``ning o'zi ishlatadigan
kutubxona, shuning uchun ``requirements.txt``ga hech narsa qo'shilmaydi.
"""

import os

from aiohttp import web


async def _health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def start(port: int | None = None) -> web.AppRunner:
    """Health-check serverini ishga tushiradi va uni to'xtatish uchun
    ``AppRunner``ni qaytaradi (``await runner.cleanup()`` bilan yopiladi).
    """
    resolved_port = port if port is not None else int(os.getenv("PORT", "10000"))

    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", resolved_port)
    await site.start()

    return runner
