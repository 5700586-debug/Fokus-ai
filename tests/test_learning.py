from repositories import checklists as checklists_repo
from services import learning


def test_is_meaningful_understanding():
    assert learning.is_meaningful_understanding("ha") is False
    assert learning.is_meaningful_understanding("Ok") is False
    assert learning.is_meaningful_understanding("tushundim") is False
    assert learning.is_meaningful_understanding("qisqa") is False
    assert learning.is_meaningful_understanding("Har kuni checklistni tekshirib chiqaman") is True


def test_submit_understanding_rejects_trivial_answer():
    checklist_id = checklists_repo.create_checklist(None, "Xavfsizlik", "Matn", created_by=1)
    progress_id = learning.assign_checklist(1, checklist_id)

    assert learning.submit_understanding(progress_id, "ha") is False

    progress = learning.get_progress_for_user(1)
    assert progress[0]["status"] == "assigned"


def test_submit_understanding_accepts_meaningful_answer():
    checklist_id = checklists_repo.create_checklist(None, "Xavfsizlik", "Matn", created_by=1)
    progress_id = learning.assign_checklist(1, checklist_id)

    assert learning.submit_understanding(progress_id, "Har safar himoya vositalarini kiyaman") is True

    progress = learning.get_progress_for_user(1)
    assert progress[0]["status"] == "understood"


def test_get_active_checklists_filters_by_role():
    checklists_repo.create_checklist("haydovchi", "Haydovchi nizomi", "Matn", created_by=1)
    checklists_repo.create_checklist(None, "Umumiy nizom", "Matn", created_by=1)
    checklists_repo.create_checklist("taminotchi", "Ta'minotchi nizomi", "Matn", created_by=1)

    haydovchi_lists = learning.get_active_checklists("haydovchi")
    titles = {c["title"] for c in haydovchi_lists}
    assert titles == {"Haydovchi nizomi", "Umumiy nizom"}
