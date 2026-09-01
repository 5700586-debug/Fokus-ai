"""``services/recruiting_redflags.py`` — mazmunga asoslangan (uzunlikka
emas) kritik xavf aniqlash testlari. Real Telegram sinovida topilgan
asosiy kamchilik: "muddati o'tgan mahsulotni sotsam bo'ladi, hech kim
bilmaydi" kabi javoblar uzun/aniq bo'lgani uchun avval YAXSHI
baholangan edi — bu fayl aynan shu holatni qamrab oladi."""

from services import recruiting_redflags as rf


# --------------------------------------------------------- muddati o'tgan --


def test_expired_product_sell_intent_is_red():
    status = rf.check_expired_product("Muddati o'tgan bo'lsa ham sotsam bo'ladi, hech kim bilmaydi")
    assert status == rf.RED


def test_expired_product_correct_action_is_green():
    status = rf.check_expired_product("Darhol javondan olib tashlayman va rahbarga aytaman")
    assert status == rf.GREEN


def test_expired_product_ambiguous_text_is_unclear():
    status = rf.check_expired_product("Bilib turaman shekilli")
    assert status == rf.UNCLEAR


def test_expired_product_empty_answer_is_unclear():
    assert rf.check_expired_product("") == rf.UNCLEAR


def test_expired_product_sell_intent_wins_when_both_signals_present():
    # "Olib tashlayman, lekin arzon bo'lsa sotib yuboraman" — sotish
    # niyati ustun, ikkilanish emas (xavfsizlik ustuvor).
    status = rf.check_expired_product("Odatda olib tashlayman, lekin ba'zan arzonlashtirib sotaman")
    assert status == rf.RED


# ------------------------------------------------------------- kamomad --


def test_shortage_avoidance_without_reporting_is_red():
    status = rf.check_shortage_response("Bu mening aybim emas, hech kimga aytmayman")
    assert status == rf.RED


def test_shortage_reporting_is_green():
    status = rf.check_shortage_response("Darhol rahbarga aytib, hisobni tekshiraman")
    assert status == rf.GREEN


def test_shortage_ambiguous_is_unclear():
    assert rf.check_shortage_response("Ko'rib chiqaman") == rf.UNCLEAR


# --------------------------------------------------- login/kassa ulashish --


def test_credential_sharing_intent_is_red():
    assert rf.check_credential_sharing("Ishongan hamkasbimga kassamni beraman") == rf.RED


def test_credential_refusal_is_green():
    assert rf.check_credential_sharing("Yo'q, hech kimga bermayman, faqat o'zim ishlataman") == rf.GREEN


# --------------------------------------------------------- xaridor mojaro --


def test_customer_conflict_escalation_is_red():
    assert rf.check_customer_conflict("Men ham baqiraman, kerak emassiz desam bo'ladi") == rf.RED


def test_customer_conflict_deescalation_is_green():
    assert rf.check_customer_conflict("Xotirjam bo'lib, tinglayman va yechim topaman") == rf.GREEN


def test_customer_conflict_ambiguous_is_unclear():
    assert rf.check_customer_conflict("Qaraymiz-da") == rf.UNCLEAR


def test_label_for_returns_human_readable_text_for_all_known_flags():
    for key in (rf.EXPIRED_PRODUCT, rf.SHORTAGE_COVERUP, rf.CREDENTIAL_SHARING, rf.CUSTOMER_CONFLICT):
        label = rf.label_for(key)
        assert label and label != key


def test_label_for_unknown_key_returns_the_key_itself_without_crashing():
    assert rf.label_for("noma'lum_kalit") == "noma'lum_kalit"
