"""O'quv/checklist progressi — jazo emas, o'rgatish uchun.

Xodim shunchaki "ha" deb javob berib ketishi qabul qilinmaydi — qisqacha
o'zi tushunganini yozishi kerak.
"""

from repositories import checklists as checklists_repo

_TRIVIAL_ANSWERS = {"ha", "ha.", "xa", "xa.", "ok", "ok.", "yes", "tushundim"}
_MIN_NOTE_LENGTH = 8


def is_meaningful_understanding(text: str) -> bool:
    normalized = text.strip().lower()
    if normalized in _TRIVIAL_ANSWERS:
        return False
    return len(normalized) >= _MIN_NOTE_LENGTH


def assign_checklist(user_id: int, checklist_id: int) -> int:
    return checklists_repo.assign_checklist(user_id, checklist_id)


def submit_understanding(progress_id: int, understanding_note: str) -> bool:
    """Mazmunsiz javob bo'lsa yozilmaydi, ``False`` qaytaradi — chaqiruvchi
    xodimdan qayta so'rashi kerak.
    """
    if not is_meaningful_understanding(understanding_note):
        return False

    checklists_repo.mark_understood(progress_id, understanding_note)
    return True


def get_active_checklists(role_key: str | None = None) -> list[dict]:
    return checklists_repo.get_active_checklists(role_key)


def get_progress_for_user(user_id: int) -> list[dict]:
    return checklists_repo.get_progress_for_user(user_id)
