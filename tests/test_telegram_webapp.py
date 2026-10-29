import hashlib
import hmac
from urllib.parse import urlencode

from services.telegram_webapp import verify_init_data


def signed(token="123:ABC", timestamp=1000, **extra):
    fields = {"auth_date": str(timestamp), "user": '{"id":7}', **extra}
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def test_valid_signature():
    assert verify_init_data(signed(), "123:ABC", now=1001)


def test_modified_data_rejected():
    assert not verify_init_data(signed().replace("%22id%22%3A7", "%22id%22%3A8"), "123:ABC", now=1001)


def test_expired_future_and_duplicate_rejected():
    assert not verify_init_data(signed(), "123:ABC", now=1001 + 86401)
    assert not verify_init_data(signed(), "123:ABC", now=999)
    assert not verify_init_data(signed() + "&auth_date=1000", "123:ABC", now=1001)


def test_missing_hash_rejected():
    assert not verify_init_data("auth_date=1000&user=test", "123:ABC", now=1001)
