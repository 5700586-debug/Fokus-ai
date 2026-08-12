from datetime import datetime, timedelta, timezone

from repositories import suppliers as suppliers_repo


def test_create_and_claim_invite_creates_supplier():
    token = suppliers_repo.create_invite("Al-Fresh MCHJ", created_by=111)

    supplier = suppliers_repo.claim_invite(token, telegram_user_id=555)

    assert supplier is not None
    assert supplier["telegram_user_id"] == 555
    assert supplier["company_name"] == "Al-Fresh MCHJ"
    assert supplier["status"] == "active"
    assert suppliers_repo.get_supplier_by_telegram_id(555)["id"] == supplier["id"]


def test_claim_invite_rejects_unknown_token():
    assert suppliers_repo.claim_invite("no-such-token", telegram_user_id=1) is None


def test_claim_invite_rejects_already_claimed_token():
    token = suppliers_repo.create_invite(None, created_by=111)
    suppliers_repo.claim_invite(token, telegram_user_id=1)

    assert suppliers_repo.claim_invite(token, telegram_user_id=2) is None


def test_claim_invite_rejects_expired_token(monkeypatch):
    token = suppliers_repo.create_invite(None, created_by=111)

    from db import get_connection

    expired_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn = get_connection()
    conn.execute("UPDATE supplier_invites SET expires_at = ? WHERE token = ?", (expired_at, token))
    conn.commit()
    conn.close()

    assert suppliers_repo.claim_invite(token, telegram_user_id=1) is None


def test_messages_are_stored_per_supplier_in_order():
    token = suppliers_repo.create_invite(None, created_by=111)
    supplier = suppliers_repo.claim_invite(token, telegram_user_id=1)

    suppliers_repo.add_message(supplier["id"], "user", "Salom")
    suppliers_repo.add_message(supplier["id"], "assistant", "Assalomu alaykum")

    history = suppliers_repo.get_recent_messages(supplier["id"])
    assert [m["content"] for m in history] == ["Salom", "Assalomu alaykum"]


def test_offer_upsert_only_touches_stated_fields():
    token = suppliers_repo.create_invite(None, created_by=111)
    supplier = suppliers_repo.claim_invite(token, telegram_user_id=1)

    suppliers_repo.upsert_offer(supplier["id"], "Kartoshka", price="3000", discount="5%")
    suppliers_repo.upsert_offer(supplier["id"], "Kartoshka", minimum_order="500kg")

    offers = suppliers_repo.list_offers(supplier["id"])
    assert len(offers) == 1
    assert offers[0]["price"] == "3000"
    assert offers[0]["discount"] == "5%"
    assert offers[0]["minimum_order"] == "500kg"


def test_list_offers_for_product_spans_multiple_suppliers():
    token_a = suppliers_repo.create_invite("A ferma", created_by=111)
    supplier_a = suppliers_repo.claim_invite(token_a, telegram_user_id=1)
    token_b = suppliers_repo.create_invite("B ferma", created_by=111)
    supplier_b = suppliers_repo.claim_invite(token_b, telegram_user_id=2)

    suppliers_repo.upsert_offer(supplier_a["id"], "Pomidor", price="4000")
    suppliers_repo.upsert_offer(supplier_b["id"], "Pomidor", price="3800")
    suppliers_repo.upsert_offer(supplier_a["id"], "Bodring", price="2000")

    offers = suppliers_repo.list_offers_for_product("Pomidor")
    companies = {o["supplier_company_name"] for o in offers}
    assert companies == {"A ferma", "B ferma"}
    assert len(offers) == 2
