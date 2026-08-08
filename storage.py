"""SQLite-backed FSM storage.

Standart MemoryStorage bot qayta ishga tushganda onboarding javoblarini
yo'qotadi. Bu storage FSM holati va to'plangan javoblarni fokus.db ga
yozadi, shuning uchun xodim onboarding jarayonini bot qayta ishga
tushgandan keyin ham davom ettira oladi.
"""

import json
from typing import Any, Dict, Mapping, Optional

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from db import get_connection


def _key_str(key: StorageKey) -> str:
    return ":".join(
        str(part)
        for part in (
            key.bot_id,
            key.chat_id,
            key.user_id,
            key.thread_id,
            key.business_connection_id,
            key.destiny,
        )
    )


class SQLiteStorage(BaseStorage):
    async def set_state(self, key: StorageKey, state: Optional[Any] = None) -> None:
        state_value = state.state if isinstance(state, State) else state
        storage_key = _key_str(key)

        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO fsm_storage (storage_key, state) VALUES (?, ?) "
                "ON CONFLICT(storage_key) DO UPDATE SET state = excluded.state",
                (storage_key, state_value),
            )
            conn.commit()
        finally:
            conn.close()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        storage_key = _key_str(key)

        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT state FROM fsm_storage WHERE storage_key = ?", (storage_key,)
            ).fetchone()
        finally:
            conn.close()

        return row["state"] if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        storage_key = _key_str(key)
        payload = json.dumps(dict(data), ensure_ascii=False)

        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO fsm_storage (storage_key, data) VALUES (?, ?) "
                "ON CONFLICT(storage_key) DO UPDATE SET data = excluded.data",
                (storage_key, payload),
            )
            conn.commit()
        finally:
            conn.close()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        storage_key = _key_str(key)

        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT data FROM fsm_storage WHERE storage_key = ?", (storage_key,)
            ).fetchone()
        finally:
            conn.close()

        if not row or not row["data"]:
            return {}

        return json.loads(row["data"])

    async def close(self) -> None:
        pass
