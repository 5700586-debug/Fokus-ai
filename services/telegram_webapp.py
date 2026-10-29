"""Pure Telegram WebApp initData signature and expiry validation. No HTTP."""
import hashlib
import hmac
import time
from urllib.parse import parse_qsl


def verify_init_data(init_data: str, bot_token: str, *, now: int | None = None, max_age: int = 86400) -> bool:
    if not isinstance(init_data, str) or not isinstance(bot_token, str) or not bot_token or max_age <= 0:
        return False
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs) or "hash" not in fields or "auth_date" not in fields:
            return False
        digest = fields.pop("hash")
        if len(digest) != 64:
            return False
        auth_date = int(fields["auth_date"])
        current = int(time.time() if now is None else now)
        if auth_date > current or current - auth_date > max_age:
            return False
        check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError, UnicodeError):
        return False
