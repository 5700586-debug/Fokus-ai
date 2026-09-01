"""``e2e/run_e2e.py``dagi diagnostika yordamchi funksiyalarini
tekshiradi. Telethon shart emas — bu funksiyalar duck-typed
obyektlar bilan ishlaydi, ``e2e.run_e2e`` moduli import qilinganda
Telethon faqat ``_run()`` funksiyasi ICHIDA (chaqirilganda) import
qilinadi, modul darajasida emas — shuning uchun oddiy Linux CI'da
credential/Telethon'siz ishlaydi."""

from e2e import run_e2e


class _FakeButton:
    def __init__(self, text):
        self.text = text


class _FakeRow:
    def __init__(self, buttons):
        self.buttons = buttons


class _FakeReplyMarkup:
    def __init__(self, rows):
        self.rows = rows


class _FakeMessage:
    def __init__(self, text=None, reply_markup=None):
        self.text = text
        self.reply_markup = reply_markup


def test_now_returns_hh_mm_ss_millis_format():
    value = run_e2e._now()

    assert len(value.split(":")) == 3
    assert "." in value


def test_extract_button_texts_returns_empty_for_no_markup():
    assert run_e2e._extract_button_texts(_FakeMessage(text="hi")) == []


def test_extract_button_texts_reads_reply_keyboard_rows_in_order():
    markup = _FakeReplyMarkup(rows=[
        _FakeRow([_FakeButton("A"), _FakeButton("B")]),
        _FakeRow([_FakeButton("C")]),
    ])
    message = _FakeMessage(text="hi", reply_markup=markup)

    assert run_e2e._extract_button_texts(message) == ["A", "B", "C"]


def test_load_config_exits_cleanly_when_secrets_missing(monkeypatch):
    for name in run_e2e._REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    import pytest

    with pytest.raises(SystemExit) as exc_info:
        run_e2e._load_config()

    assert exc_info.value.code == 2
