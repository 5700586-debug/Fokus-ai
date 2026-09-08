"""``main._SandboxPreviewMiddleware`` va ``main._ClearStaleStateMiddleware``
— ikkalasi ham HAR BIR Telegram Update uchun ishlaydigan ikkita eng
tashqi ``dp.update.outer_middleware`` — endi keraksiz PostgreSQL FSM
storage (``storage.py`` -> ``db.get_connection()``) so'rovlarini olib
tashlagan: preview FAQAT ENVIRONMENT=test'dagi Founder uchun
``state.get_data()``ga yetadi (boshqa hamma uchun zudlik pastga
o'tkaziladi), stale-state tekshiruvi esa aiogram'ning o'zi allaqachon
hisoblab qo'ygan ``data["raw_state"]`` keshidan foydalanadi va
``state.get_state()``ni ikki marta emas, zaxira holatidagina (va faqat
bir marta) chaqiradi.

Bu fayl middleware'larni TO'G'RIDAN-TO'G'RI, real bot dispatcher/DB
orqali EMAS, soxta ``state``/``event``/``handler`` obyektlari bilan
sinaydi — maqsad XATTI-HARAKATNI (qaysi chaqiruvlar sodir bo'ladi,
qaysilari bo'lmaydi) tekshirish, matn/implementatsiya detalini emas.
"""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeState:
    """``aiogram.fsm.context.FSMContext``ning minimal soxta versiyasi —
    har bir metod chaqiruvini sanaydi, shu orqali testlar ANIQ nechta
    marta chaqirilganini tekshira oladi."""

    def __init__(self, raw_state=None, data=None):
        self._raw_state = raw_state
        self._data = dict(data or {})
        self.get_data_calls = 0
        self.get_state_calls = 0
        self.clear_calls = 0
        self.update_data_calls = 0

    async def get_data(self):
        self.get_data_calls += 1
        return dict(self._data)

    async def get_state(self):
        self.get_state_calls += 1
        return self._raw_state

    async def clear(self):
        self.clear_calls += 1
        self._raw_state = None
        self._data = {}

    async def update_data(self, **kwargs):
        self.update_data_calls += 1
        self._data.update(kwargs)


class _FakeMessage:
    def __init__(self, user_id: int, text: str | None):
        self.from_user = SimpleNamespace(id=user_id)
        self.text = text
        self.sent: list[str] = []

    async def answer(self, text, reply_markup=None):
        self.sent.append(text)


def _event(message=None, callback_query=None):
    return SimpleNamespace(message=message, callback_query=callback_query)


async def _passthrough_handler(event, data):
    return "handled"


# ------------------------------------------------- _SandboxPreviewMiddleware --


async def test_sandbox_preview_passes_through_without_state_read_in_production(monkeypatch):
    import main

    monkeypatch.setattr(main, "ENVIRONMENT", "production")

    state = _FakeState()
    message = _FakeMessage(main.FOUNDER_ID, "istalgan matn")
    event = _event(message=message)
    data = {"state": state}

    result = await main._SandboxPreviewMiddleware()(_passthrough_handler, event, data)

    assert result == "handled"
    assert state.get_data_calls == 0


async def test_sandbox_preview_passes_through_for_non_founder_in_test_env(monkeypatch):
    import main

    monkeypatch.setattr(main, "ENVIRONMENT", "test")

    state = _FakeState()
    non_founder_id = main.FOUNDER_ID + 1
    message = _FakeMessage(non_founder_id, "istalgan matn")
    event = _event(message=message)
    data = {"state": state}

    result = await main._SandboxPreviewMiddleware()(_passthrough_handler, event, data)

    assert result == "handled"
    assert state.get_data_calls == 0


async def test_founder_preview_entry_still_works_in_test_env(monkeypatch):
    import main

    monkeypatch.setattr(main, "ENVIRONMENT", "test")

    state = _FakeState()
    message = _FakeMessage(main.FOUNDER_ID, main._ROLE_TEST_ENTRY_TEXT)
    event = _event(message=message)
    data = {"state": state}

    async def _handler_should_not_be_called(event, data):
        raise AssertionError("preview aktiv bo'lganda real handler chaqirilmasligi kerak")

    result = await main._SandboxPreviewMiddleware()(_handler_should_not_be_called, event, data)

    assert result is None
    assert state.get_data_calls == 1
    assert state.update_data_calls == 1
    assert state._data.get("preview_picking") is True
    assert message.sent and "Qaysi rolni sinab ko'rmoqchisiz?" in message.sent[0]


# ---------------------------------------------- _ClearStaleStateMiddleware --


async def test_clear_stale_state_uses_cached_raw_state_without_get_state_call():
    import main

    state = _FakeState(raw_state=None)
    message = _FakeMessage(1, "oddiy xabar")
    event = _event(message=message)
    data = {"state": state, "raw_state": None}

    result = await main._ClearStaleStateMiddleware()(_passthrough_handler, event, data)

    assert result == "handled"
    assert state.get_state_calls == 0


async def test_escape_command_with_stale_raw_state_clears_exactly_once():
    import main

    state = _FakeState(raw_state="SomeStates:step")
    message = _FakeMessage(1, "/openshift")
    event = _event(message=message)
    data = {"state": state, "raw_state": "SomeStates:step"}

    await main._ClearStaleStateMiddleware()(_passthrough_handler, event, data)

    assert state.clear_calls == 1
    assert data["raw_state"] is None
    assert state.get_state_calls == 0


async def test_non_escape_message_does_not_clear_state():
    import main

    state = _FakeState(raw_state="SomeStates:step")
    message = _FakeMessage(1, "shunchaki oddiy matn")
    event = _event(message=message)
    data = {"state": state, "raw_state": "SomeStates:step"}

    await main._ClearStaleStateMiddleware()(_passthrough_handler, event, data)

    assert state.clear_calls == 0
    assert data["raw_state"] == "SomeStates:step"


async def test_missing_raw_state_falls_back_to_get_state_at_most_once():
    import main

    state = _FakeState(raw_state="SomeStates:step")
    message = _FakeMessage(1, "/openshift")
    event = _event(message=message)
    data = {"state": state}  # ATAYLAB "raw_state" kaliti yo'q

    await main._ClearStaleStateMiddleware()(_passthrough_handler, event, data)

    assert state.get_state_calls == 1
    assert state.clear_calls == 1
    assert data["raw_state"] is None
