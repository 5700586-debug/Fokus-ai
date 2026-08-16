"""Saturn tonggi/tungi rasmli xabari uchun qisqa foydali maslahat matni.

Ikki mustaqil, qo'lda tekshirilgan bank: tonggi (operatsion — xizmat,
muomala, tozalik, jamoaviylik, diqqat, rivojlanish, sog'liq) va tungi
(kun yakuni — dam olish, minnatdorchilik, ertangi kunga tayyorgarlik).
Ikkalasi ham tibbiy/huquqiy/siyosiy/bahsli mazmundan XOLI — har bir
matn qo'lda yozilgan va tekshirilgan (AI tomonidan TO'QILMAGAN).

AI (mavjud bo'lsa) faqat TANLANGAN bank matnini boshqacha so'z bilan
qayta ifodalash uchun ishlatiladi — yangi mavzu o'ylab topmaydi, faqat
bor matnni "yangilaydi". Natija uzunlik va bo'shlik bo'yicha tekshiriladi
— mos kelmasa yoki AI ishlamasa, original bank matni o'zgarishsiz
ishlatiladi (xabar yuborish hech qachon to'xtamaydi).

Oxirgi 30 kunda (aniqrog'i — oxirgi 30 ta shu turdagi post) ishlatilgan
mavzu qayta tanlanmaydi (``repositories/saturn_group.get_recent_content_keys``).
"""

import logging

from openai import AsyncOpenAI

from repositories import saturn_group as saturn_repo

logger = logging.getLogger(__name__)

_MODEL = "gpt-5-mini"
_MAX_ADVICE_LENGTH = 130  # 120 belgilik maqsaddan biroz xavfsizlik zaxirasi bilan

# ------------------------------------------------------------- tonggi bank --
# Mavzular: savdo/xizmat, muomala, tozalik/tartib, mahsulot joylash,
# jamoaviylik, diqqat, rivojlanish, ishni yengillashtirish, sog'liq.
MORNING_ADVICE_BANK: list[tuple[str, str]] = [
    ("m_sav_1", "Xaridor eshikdan kirgan zahoti tabassum bilan salomlashing — birinchi taassurot doim yodda qoladi."),
    ("m_sav_2", "Xaridorni tinglang, gapini bo'lmang — nima izlayotganini aniq bilib, keyin taklif bering."),
    ("m_sav_3", "Xaridorga faqat kerakli emas, mos qo'shimcha mahsulotni ham taklif qiling — ikkalasiga foyda."),
    ("m_sav_4", "Savol beruvchi xaridorni hech qachon shoshiltirmang — sabr ishonchni mustahkamlaydi."),
    ("m_sav_5", "Kassada navbat uzayganda ham xotirjamlikni saqlang — shoshilish xato qildiradi."),
    ("m_sav_6", "Mahsulot haqida savol bersa, bilmagan narsangizni yashirmang — so'rab, keyin aniq javob bering."),
    ("m_muo_1", "Norozi xaridorni ayblab yoki oqlab qo'ymang — avval to'liq tinglang, keyin yechim toping."),
    ("m_muo_2", "Xaridorga ismi bilan murojaat qilish (bilsangiz) ishonchni sezilarli oshiradi."),
    ("m_muo_3", "Janjal chiqsa, ovozingizni ko'tarmang — xotirjamlik eng kuchli javobdir."),
    ("m_muo_4", "Kimningdir kayfiyati yomon bo'lsa, buni shaxsiy qabul qilmang — samimiy muomala saqlang."),
    ("m_muo_5", "Xaridorga yolg'on va'da bermang — mahsulot haqida faqat aniq bilganingizni ayting."),
    ("m_muo_6", "Kutish vaqti uzunroq bo'lsa, xaridorga buni bildirib qo'ying — noaniqlik norozilik keltiradi."),
    ("m_toz_1", "Toza vitrina va tartibli javon — xaridor birinchi ko'radigan va baholaydigan narsa."),
    ("m_toz_2", "Smena boshida va oxirida ish joyingizni tekshirib chiqing — kichik tartib katta taassurot beradi."),
    ("m_toz_3", "Chang bosgan yoki muddati o'tgan mahsulotni har kuni tekshiring — bu ishonchni saqlaydi."),
    ("m_toz_4", "Ish kiyimingiz va tashqi ko'rinishingiz ham xaridor uchun kompaniyaning vizitkasidir."),
    ("m_joy_1", "Ko'p sotiladigan mahsulotni ko'z balandligida joylashtiring — bu tasodifiy xaridni oshiradi."),
    ("m_jam_1", "Hamkasbingizga yordam qo'lini cho'zing — jamoa ruhi kichik yordamlardan mustahkamlanadi."),
    ("m_jam_2", "Bugun kimgadir rahmat ayting — kichik minnatdorchilik kayfiyatni butun kunga yaxshilaydi."),
    ("m_jam_3", "Yangi hamkasbingizga savol berishdan tortinmang — birga ishlash tezroq o'rgatadi."),
    ("m_jam_4", "Rahbaringiz yoki hamkasbingiz fikr bildirsa, uni tinglang — bu sizning o'sishingizga yordam beradi."),
    ("m_diq_1", "Ishni boshlashdan oldin bugungi asosiy 3 vazifangizni aniqlab oling — diqqat tarqalmaydi."),
    ("m_diq_2", "Telefon bilan ovora bo'lib, xaridorni ko'zdan qochirmang — u sizni kuzatayotganini unutmang."),
    ("m_diq_3", "Bugun bironta ishni \"keyinroq\" demasdan, darhol bajarib qo'yishga harakat qiling."),
    ("m_riv_1", "Har kuni bitta yangi narsa o'rganishga harakat qiling — kichik qadamlar katta natija beradi."),
    ("m_riv_2", "Xato qilsangiz, uni yashirmang — tan olish va tuzatish rivojlanishning eng qisqa yo'li."),
    ("m_riv_3", "Kichik muvaffaqiyatlaringizni ham qadrlang — ular katta natijaning bir qismi."),
    ("m_yen_1", "Ish boshida kerakli buyum va hujjatlarni tayyorlab qo'ying — kun davomida vaqt tejaydi."),
    ("m_yen_2", "Takrorlanadigan ishni soddalashtirish yo'lini toping — kichik o'zgarish ko'p vaqt tejaydi."),
    ("m_vaq_1", "Kun boshida rejani tuzib oling — nima qachon bajarilishini bilish tashvishni kamaytiradi."),
    ("m_sal_1", "Kuniga yetarlicha suv iching — chanqoqlik sezguningizcha kutmang, diqqat susayadi."),
    ("m_sal_2", "Ish orasida yengil va o'z vaqtida ovqatlaning — och qorin xatolarni ko'paytiradi."),
    ("m_sal_3", "Har 1-2 soatda 2-3 daqiqa turib cho'zilib oling — uzoq bir holatda turish charchoqni oshiradi."),
    ("m_sal_4", "Yetarli uxlash diqqat va xushmuomalalikni saqlaydi — bugun ertaroq yotishga harakat qiling."),
    ("m_gig_1", "Mahsulot va pul bilan ishlaganda qo'l gigiyenasiga alohida e'tibor bering."),
    ("m_sav_7", "Xaridor ikkilanib turgan bo'lsa, bosim qilmang — savollariga sabr bilan javob bering, qaror unga tegishli."),
    ("m_sav_8", "Yangi mahsulot kelganda uni xaridorga qisqa va aniq tanishtiring — ortiqcha maqtovsiz, foydasini ayting."),
    ("m_sav_9", "Xaridor xato mahsulot olib kelib qaytarsa, xafa bo'lmang — xotirjam yordam bering, bu ham xizmatning bir qismi."),
    ("m_toz_5", "Yerga tushgan mahsulot yoki chiqindini darhol yig'ishtiring — kutib turish xavf va nojo'ya ko'rinish yaratadi."),
    ("m_toz_6", "Kassa atrofi va mijozlar kutadigan joyni ham tartibda tuting — xaridor faqat javonni emas, hammasini ko'radi."),
    ("m_toz_7", "Hidli yoki buzilgan mahsulotni darhol chetga oling — bu xaridor sog'lig'i va ishonchi uchun muhim."),
    ("m_jam_5", "Hamkasbingiz charchagan yoki qiynalayotgan bo'lsa, so'rab qo'ying — kichik e'tibor katta yordam bo'lishi mumkin."),
    ("m_jam_6", "Yangi vazifa taqsimlanganda o'z hissangizni to'liq bajaring — jamoa har birimizning ulushiga tayanadi."),
    ("m_jam_7", "Kelishmovchilik chiqsa, gapni ochiq va hurmat bilan gaplashib hal qiling — ich-ichdan xafa bo'lib yurmang."),
    ("m_riv_4", "Hamkasbingizdan yaxshi bilgan bir usulini so'rab o'rganing — bu sizga ham, jamoaga ham foyda beradi."),
    ("m_riv_5", "Bugun bir yangi vazifani o'z ixtiyoringiz bilan qo'lga oling — tashabbus ko'rsatish rivojlanish belgisi."),
    ("m_riv_6", "O'z ishingizni tugatgach, boshqa nima yordam bera olishingizni so'rang — bu jamoada qadrlanadi."),
    ("m_vaq_2", "Smenangizga bir necha daqiqa oldin yetib keling — tayyor holda boshlash kunni yengil qiladi."),
    ("m_vaq_3", "Kechikib qolsangiz, buni oldindan xabar qiling — bu hamkasblaringizga hurmat belgisidir."),
    ("m_vaq_4", "Tanaffusdan o'z vaqtida qayting — bu ishning davomiyligiga va jamoaga bo'lgan hurmatga bog'liq."),
    ("m_joy_2", "Mahsulotni javonga qo'yishda eski sanalisini oldinga, yangisini orqaga joylashtiring — bu isrofni kamaytiradi."),
    ("m_joy_3", "Bo'sh yoki notekis javonni bugun tekshirib, tartibga soling — xaridor uchun izlash osonlashadi."),
    ("m_joy_4", "Narx yorlig'i mahsulotga mos ekanini har kuni tekshiring — noaniqlik xaridor ishonchini yo'qotadi."),
    ("m_kas_1", "Kassani boshqa birovga topshirib, o'zingiz uzoqlashmang — hisob-kitob faqat sizning javobgarligingizda bo'lsin."),
    ("m_kas_2", "Har bir chekni mijozga berishdan oldin summani diqqat bilan tekshiring — shoshilinch xato ishonchni buzadi."),
    ("m_kas_3", "Smena tugaganda kassani ikki marta tekshirib, keyin topshiring — bu o'zingizni ham himoya qiladi."),
    ("m_kas_4", "Naqd pul bilan ishlaganda diqqatingizni faqat shu ishga qarating — bir vaqtda ikki ishni qilmang."),
    ("m_kas_5", "Kassadagi nomuvofiqlikni sezsangiz, darhol rahbarga ayting — yashirish emas, ochiqlik to'g'ri yo'l."),
    ("m_log_1", "Shaxsiy login yoki parolingizni hech kimga bermang — bu sizning ishingiz va mas'uliyatingiz belgisidir."),
    ("m_log_2", "Tizimga boshqa birovning hisobi bilan kirmang — har bir amal aniq bir kishiga tegishli bo'lishi kerak."),
    ("m_log_3", "Ish joyidan ketayotganda tizimdan chiqishni unutmang — bu kichik odat, katta xavfsizlik beradi."),
    ("m_narx_1", "Mahsulot narxini aniq bilmasangiz, taxmin qilmang — tekshirib, keyin xaridorga to'g'ri ayting."),
    ("m_narx_2", "Aksiya yoki chegirma haqida noaniq gapirmang — shartlarini avval o'zingiz aniq bilib oling."),
    ("m_narx_3", "Mahsulot tarkibi yoki muddati haqida so'rasa, qadoqdagi ma'lumotni birga ko'rib tasdiqlang."),
    ("m_tel_1", "Ish vaqtida shaxsiy telefon suhbatini keyinga qoldiring — xaridor kutib turganini unutmang."),
    ("m_tel_2", "Zarur qo'ng'iroq bo'lsa, xaridordan bir necha soniya kechirim so'rab, tez tugating."),
    ("m_tel_3", "Ijtimoiy tarmoqni faqat tanaffusda ko'ring — ish vaqti to'liq xaridorga bag'ishlansin."),
    ("m_qsh_1", "Qo'shimcha mahsulotni faqat mos kelganda taklif qiling — bosim emas, foydali maslahat sifatida ayting."),
    ("m_qsh_2", "Xaridor \"yo'q\" desa, darhol to'xtating — qayta-qayta taklif qilish noqulaylik tug'diradi."),
    ("m_qsh_3", "Taklif qilayotgan mahsulotingizni o'zingiz yaxshi bilib gapiring — bu ishonchli tuyuladi."),
    ("m_ozt_1", "Band yoki asabiy vaqtda ham ovozingizni past va xotirjam saqlang — bu vaziyatni yengillashtiradi."),
    ("m_ozt_2", "G'azablangan his qilsangiz, bir chuqur nafas oling va keyin javob bering — shoshilib gapirmang."),
    ("m_ozt_3", "Qiyin kunda ham hamkasbingizga qattiq gapirmang — charchoq bahona bo'lmasin."),
    ("m_ozt_4", "Stressli vaziyatdan keyin bir necha daqiqa o'zingizni tinchlantiring, keyin ishga qayting."),
    ("m_yech_1", "Muammo chiqsa, \"iloji yo'q\" demasdan, avval bitta yechim variantini taklif qiling."),
    ("m_yech_2", "Xato yuz bersa, sababini izlash o'rniga, avval uni qanday tuzatishni o'ylang."),
    ("m_yech_3", "Yechimni topa olmasangiz, yolg'iz qolmang — hamkasb yoki rahbardan maslahat so'rang."),
    ("m_yech_4", "Har bir muammoni o'rganish imkoniyati deb qarang — bu kayfiyatingizni ham yengillashtiradi."),
    ("m_mas_1", "O'z zimmangizga olgan ishni oxirigacha yetkazing — yarim qoldirilgan ish jamoaga qiyinchilik tug'diradi."),
    ("m_mas_2", "Xato qilsangiz, uni tan oling — bu ayb emas, mas'uliyatli xodimning belgisi."),
    ("m_mas_3", "Vazifani unutmaslik uchun yozib qo'ying — \"esimda qoladi\" deb ishonmang."),
    ("m_mas_4", "Bergan va'dangizni bajaring — kichik va'da ham xaridor va hamkasb ishonchini shakllantiradi."),
    ("m_smn_1", "Smenani tugatishdan oldin ish joyingizni keyingi xodim uchun tayyor holga keltiring."),
    ("m_smn_2", "Muhim voqea yoki qoldirilgan ishni keyingi smenaga aniq aytib o'ting — noaniqlik xatoga olib keladi."),
    ("m_smn_3", "Asboblar va materiallarni o'z joyiga qaytarib qo'ying — keyingi xodim izlab vaqt yo'qotmasin."),
    ("m_smn_4", "Smena topshirishda shoshilmang — bir necha daqiqa ajratib, hammasini aniq tushuntiring."),
    ("m_xvf_1", "Og'ir yoki noqulay yukni ko'targanda orqangizga emas, tizzangizga tayaning — bu tanangizni asraydi."),
    ("m_xvf_2", "Nam yoki sirg'anchiq polni darhol belgilab qo'ying — hodisaning oldini olish kutishdan yaxshi."),
    ("m_xvf_3", "Elektr asboblardan foydalanganda ko'rsatmalarga qat'iy amal qiling — shoshilinch xavf tug'diradi."),
    ("m_xvf_4", "Xavfli holatni ko'rsangiz, jim o'tirmang — darhol hamkasb yoki rahbarga xabar bering."),
]

# -------------------------------------------------------------- tungi bank --
# Mavzular: dam olish, minnatdorchilik, ertangi kunga tayyorgarlik,
# ish joyini tartibga solish, ijobiy fikrlash, uyqu.
NIGHT_ADVICE_BANK: list[tuple[str, str]] = [
    ("n_tartib_1", "Ish joyini tartibli qoldirish — ertangi kunni yengil boshlash demakdir."),
    ("n_minnat_1", "Bugun qilgan mehnatingiz uchun o'zingizga rahmat ayting — har kun qadr-qimmatga loyiq."),
    ("n_tayyor_1", "Ertangi kun uchun ustuvor bitta vazifani bugunoq belgilab qo'ying."),
    ("n_uyqu_1", "Uxlashdan oldin telefonni chetga qo'ying — sifatli dam olish ertangi kunni yengillashtiradi."),
    ("n_oila_1", "Uyga qaytganingizda oilangiz bilan bugungi kun haqida gaplashib, ulushib oling."),
    ("n_ijobiy_1", "Bugun nima yaxshi ketgani haqida bir daqiqa o'ylab ko'ring — kichik yutuqlar ham muhim."),
    ("n_tartib_2", "Ertaga kerak bo'ladigan narsalarni bugun kechqurun tayyorlab qo'yish vaqtni tejaydi."),
    ("n_dam_1", "Ish va dam olish orasida chegara qo'ying — ertangi kuchingiz shu dam olishga bog'liq."),
    ("n_minnat_2", "Bugun sizga yordam bergan hamkasbingizga xabar yozib, rahmat ayting."),
    ("n_ijobiy_2", "Kamchilikka emas, ertangi imkoniyatga e'tibor qarating — har kun yangi boshlanish."),
    ("n_uyqu_2", "Erta yotish — ertangi kunni yangi kuch bilan boshlashning eng oddiy yo'li."),
    ("n_tayyor_2", "Ertangi rejangizni ko'zdan kechiring — noaniqlik kamaysa, tinch uxlaysiz."),
    ("n_oila_2", "Kichik bo'lsa ham, sevganlaringiz bilan birga o'tkazgan daqiqalar eng qimmatli."),
    ("n_dam_2", "Bugun charchagan bo'lsangiz, bu tabiiy — ertaga dam olib, yangi kuch bilan kelasiz."),
    ("n_tartib_3", "Kunlik ro'yxatingizni tekshirib, bajarilganini belgilang — bu tinchlik his qildiradi."),
    ("n_ijobiy_3", "Har kun mukammal bo'lishi shart emas — muhimi, harakat qilishda davom etish."),
    ("n_minnat_3", "Bugun sizga tabassum ulashgan xaridorni eslang — yaxshilik yaxshilikni tug'diradi."),
    ("n_dam_3", "Uyqudan oldin bugungi tashvishlarni qog'ozga yozib qo'yish ongni tinchlantiradi."),
    ("n_tayyor_3", "Ertangi kiyim va buyumlaringizni oldindan tayyorlab qo'ying — tong shoshilinch o'tmaydi."),
    ("n_oila_3", "Uyga yetib borganingizda, bir daqiqa to'xtab, chuqur nafas oling — kun tugadi."),
    ("n_ijobiy_4", "Bugungi qiyinchilik ertangi tajribangizga aylanadi — bu ham o'tadi."),
    ("n_uyqu_3", "Yotishdan oldin xona havosini yangilash uyqu sifatini yaxshilaydi."),
    ("n_tartib_4", "Stol ustini tozalab qoldirish — ertaga ishga tez kirishishga yordam beradi."),
    ("n_minnat_4", "Bugun kimdir sizga yordam berdimi? Buni unutmang va imkon bo'lsa, javob qaytaring."),
    ("n_dam_4", "Ekrandan bir muddat uzoqlashish — ko'z va ongga dam berishning oddiy yo'li."),
    ("n_tayyor_4", "Ertangi transport yoki yo'l vaqtini bugun rejalashtirib qo'yish sarosimani kamaytiradi."),
    ("n_ijobiy_5", "Xayrli tun — ertaga yana yangi imkoniyatlar kutmoqda."),
    ("n_oila_4", "Kun davomida band bo'lgan bo'lsangiz ham, yaqinlaringizga bir necha iliq so'z ayting."),
    ("n_tartib_5", "Kerakli hujjat yoki buyumni joyiga qo'yib chiqish — ertangi izlanishni oldini oladi."),
    ("n_minnat_5", "Bugun o'z ustingizda qilgan kichik mehnatingiz uchun ham o'zingizni tabriklang."),
    ("n_dam_5", "Uzoq kun charchoq keltirsa ham, ertaga yangi kuch bilan kelishga ishoning."),
    ("n_tartib_6", "Ertaga kerak bo'lgan buyumlarni bugun kechqurun tayyor joyga qo'ying — tong shoshilmasdan boshlanadi."),
    ("n_tartib_7", "Ish stoli yoki javonni bo'sh qoldirmang — ertaga kirganingizda his qiladigan tinchlik muhim."),
    ("n_tartib_8", "Kunlik vazifalaringizni ko'zdan kechirib, tugallanmaganini ertangi ro'yxatga aniq yozib qo'ying."),
    ("n_minnat_6", "Bugun sizga yaxshi so'z aytgan kishini eslang — bu kichik iliqlik uzoq umr ko'radi."),
    ("n_minnat_7", "O'zingizga ham rahmat ayting — bugungi kichik-katta har bir sa'y-harakat qadrga loyiq."),
    ("n_tayyor_5", "Ertangi kunni yaxshi boshlash uchun bugun kechqurun bitta aniq maqsad belgilang."),
    ("n_tayyor_6", "Ertaga uchrashadigan vazifalarni xayolan bir bor ko'rib chiqing — bu ishonchni oshiradi."),
    ("n_tayyor_7", "Kechqurun ertangi kiyim va buyumlarni tayyorlab qo'yish tongni sokin qiladi."),
    ("n_uyqu_4", "Yotishdan oldin yorug' ekrandan uzoqlashing — bu ko'zga ham, uyquga ham foyda beradi."),
    ("n_uyqu_5", "Uxlashdan oldin bir necha marta sekin va chuqur nafas oling — tanangiz tinchlanadi."),
    ("n_uyqu_6", "Kechqurun ortiqcha yeb-ichishdan saqlaning — bu uyqu sifatiga bevosita ta'sir qiladi."),
    ("n_oila_5", "Uyga yetganingizda telefonni bir chetga qo'yib, atrofingizga e'tibor bering."),
    ("n_oila_6", "Yaqiningiz bilan hech bo'lmasa bir necha daqiqa ko'zma-ko'z gaplashing — bu kunni yumshatadi."),
    ("n_ijobiy_6", "Bugun qiyin bo'lgan bir lahzani eslab, undan nima o'rganganingizni o'ylab ko'ring."),
    ("n_ijobiy_7", "Ertangi kun bugungidan yaxshiroq bo'lishi mumkin — bu ishonch bilan uxlang."),
    ("n_ijobiy_8", "Kichik yutuqlaringizni ham katta deb bilib, o'zingizni qadrlashni unutmang."),
    ("n_dam_6", "Bugun tanangiz charchagan bo'lsa, uni tinglang — erta dam olish ertaga kuch beradi."),
    ("n_dam_7", "Ish haqidagi o'yni uyga olib kelmang — kechqurun vaqtingiz o'zingizga tegishli."),
    ("n_mij_1", "Bugun sizga tabassum bilan rahmat aytgan xaridorni eslang — bu xizmatingiz samarasi edi."),
    ("n_mij_2", "Qiyin xaridor bilan sabr qilganingizni o'ylab, o'zingizni tabriklang — bu oson emas edi."),
    ("n_mij_3", "Ertaga yangi xaridorlarni yana samimiy kutib olishga tayyor bo'ling — har kun yangi imkoniyat."),
    ("n_mij_4", "Bugun bir xaridorga aniq va foydali javob bergan bo'lsangiz, bu kichik, lekin qimmatli hissa."),
    ("n_mij_5", "Xizmatingizdan mamnun bo'lgan xaridor — bugungi eng yaxshi natijalardan biri, buni his eting."),
    ("n_mij_6", "Ertaga xaridor bilan muomalada birinchi taassurot yana sizning qo'lingizda ekanini unutmang."),
    ("n_mij_7", "Bugun xaridorga sabr bilan tushuntirganingiz uchun o'zingizni yaxshi his qiling."),
    ("n_mij_8", "Xizmat — kichik lahzalardan yig'iladi, bugungi har bir yaxshi muomalangiz shundan biri edi."),
    ("n_toz_1", "Ketishdan oldin ish joyingizni bir bor ko'zdan kechiring — toza joy ertangi kunni yengillashtiradi."),
    ("n_toz_2", "Bugun tartibga keltirgan javon yoki stol — ertaga sizga ham, hamkasbingizga ham qulaylik beradi."),
    ("n_toz_3", "Kichik chang yoki tartibsizlikni ham e'tiborsiz qoldirmang — bu odat kunlik ko'nikmaga aylanadi."),
    ("n_toz_4", "Ish joyini toza topshirish — keyingi smenaga ko'rsatgan hurmatingizning bir belgisi."),
    ("n_toz_5", "Bugun tozalikka ajratgan har bir daqiqangiz ertangi tez va qulay boshlanishga xizmat qiladi."),
    ("n_toz_6", "Ketishdan oldin qoldiq yoki chiqindi qolmaganini tekshiring — kichik odat katta farq qiladi."),
    ("n_toz_7", "Toza va tartibli ish joyi — xaridor va hamkasblar uchun ham yaxshi taassurot qoldiradi."),
    ("n_toz_8", "Bugun tartibni saqlaganingiz uchun rahmat — bu ertangi kuningizni ham osonlashtiradi."),
    ("n_jam_1", "Bugun sizga yordam bergan hamkasbingizni eslang — ertaga siz ham shunday yordam bera olasiz."),
    ("n_jam_2", "Jamoa bilan birga o'tkazgan bugungi kun uchun ichingizdan rahmat ayting."),
    ("n_jam_3", "Ertaga hamkasbingizga yordam qo'lini cho'zishni bugundan rejalashtiring."),
    ("n_jam_4", "Bugun kimgadir yaxshi so'z aytgan bo'lsangiz, bu jamoa ruhini mustahkamlagan ishdir."),
    ("n_jam_5", "Kelishmovchilik bo'lgan bo'lsa, ertangi kunni yangi sahifa deb bilib, ochiq muomalaga tayyor bo'ling."),
    ("n_jam_6", "Jamoadoshingizning bugungi mehnatini ham qadrlashni unutmang — hammaning hissasi muhim."),
    ("n_jam_7", "Ertaga jamoaga qanday foydali bo'lishingiz mumkinligini bir lahza o'ylab ko'ring."),
    ("n_jam_8", "Bugun birga ishlagan hamkasblaringizga xayrli tun tilang — kichik e'tibor ko'p narsani anglatadi."),
    ("n_xvf_1", "Ketishdan oldin ish joyida xavfli qolgan narsa yo'qligini bir bor tekshiring."),
    ("n_xvf_2", "Elektr asboblar va uskunalarni to'g'ri o'chirib, joyiga qo'yganingizga ishonch hosil qiling."),
    ("n_xvf_3", "Bugun sezgan kichik xavfni ertangi kun uchun eslab, hamkasblarga ham aytib qo'ying."),
    ("n_xvf_4", "Chiqishdan oldin eshik va derazalarning xavfsiz yopilganini tekshirish — kichik, lekin muhim odat."),
    ("n_xvf_5", "Bugun xavfsizlik qoidalariga rioya qilganingiz uchun o'zingizni tabriklang."),
    ("n_xvf_6", "Ertaga ham xavfsizlikni birinchi o'ringa qo'yishni unutmang — bu hammaning manfaati."),
    ("n_xvf_7", "Nam yoki sirg'anchiq joy qolmaganini ketishdan oldin tekshirib chiqing."),
    ("n_xvf_8", "Xavfsiz ish odati — bir kunlik emas, har kunlik kichik e'tibordan iborat, bugun buni davom ettirdingiz."),
    ("n_riv_1", "Bugun o'rgangan bitta yangi narsani xayolingizda mustahkamlab, uxlashga tayyorlaning."),
    ("n_riv_2", "Ertaga o'zingizni biroz yaxshiroq qilish uchun bitta kichik qadam belgilang."),
    ("n_riv_3", "Bugungi xatongizni ayb emas, ertangi saboq deb bilib, xotirjam uxlang."),
    ("n_riv_4", "Har kun kichik bir yaxshilanish — vaqt davomida katta natijaga aylanadi, bugun ham shunday bo'ldi."),
    ("n_riv_5", "Ertaga o'zingizga qiyinroq, lekin foydali bitta vazifa tanlashni o'ylab ko'ring."),
    ("n_riv_6", "Bugun qanday o'sganingizni his qilmasangiz ham, kichik izlar albatta qolgan."),
    ("n_riv_7", "Ertangi kun uchun o'zingizga bitta ijobiy so'z ayting — bu ertalabki kayfiyatga ta'sir qiladi."),
    ("n_riv_8", "Rivojlanish shoshilinch emas — bugungi sabringiz ham shu yo'lning bir qismi."),
    ("n_riv_9", "Ertaga yana bir qadam oldinga qo'yishga tayyor bo'ling — har kun yangi imkoniyat."),
]


# --------------------------------------------------- kategoriya guruhlari --
# Har bir bank kaliti (masalan "m_kas_2") allaqachon mavzu prefiksini
# o'zida saqlaydi ("kas") — buni ajratib, kengroq "rotatsiya
# kategoriyasi"ga (masalan "intizom") solishtiramiz. Yangi ustun/jadval
# shart emas — mavjud kalit formatidan foydalaniladi (haftalik mavzu
# muvozanati va "ketma-ket kunda bir xil kategoriya takrorlanmasin"
# qoidasi shu asosda ishlaydi).
_MORNING_CATEGORY_BUCKETS: dict[str, str] = {
    "sav": "xizmat", "muo": "xizmat", "qsh": "xizmat", "narx": "xizmat",
    "toz": "tozalik", "joy": "tozalik",
    "jam": "jamoa",
    "vaq": "intizom", "tel": "intizom", "ozt": "intizom", "xvf": "intizom",
    "kas": "intizom", "log": "intizom", "diq": "intizom",
    "riv": "rivojlanish", "yech": "rivojlanish", "mas": "rivojlanish",
    "smn": "rivojlanish", "yen": "rivojlanish",
    "sal": "salomatlik", "gig": "salomatlik",
}

_NIGHT_CATEGORY_BUCKETS: dict[str, str] = {
    "tartib": "tozalik", "toz": "tozalik",
    "minnat": "jamoa", "jam": "jamoa", "oila": "jamoa",
    "tayyor": "rivojlanish", "riv": "rivojlanish", "ijobiy": "rivojlanish",
    "uyqu": "salomatlik", "dam": "salomatlik",
    "mij": "xizmat",
    "xvf": "intizom",
}


def _key_prefix(key: str) -> str:
    parts = key.split("_")
    return "_".join(parts[1:-1])


def morning_category_of(key: str) -> str:
    return _MORNING_CATEGORY_BUCKETS.get(_key_prefix(key), "boshqa")


def night_category_of(key: str) -> str:
    return _NIGHT_CATEGORY_BUCKETS.get(_key_prefix(key), "boshqa")


def is_valid_advice(text: str | None) -> bool:
    """Uzun yoki bo'sh matnni rad etadi — bunday holatda chaqiruvchi
    original (tayyor bank) matnini ishlatishi kerak. Matn AVTOMATIK
    QISQARTIRILMAYDI (noqulay yarim jumla chiqmasligi uchun) — yoki
    to'liq mos, yoki butunlay rad etiladi.
    """
    if not text or not text.strip():
        return False
    return len(text.strip()) <= _MAX_ADVICE_LENGTH


def _pick_from_bank(
    bank: list[tuple[str, str]],
    post_type: str,
    category_of,
    lookback: int = 90,
) -> tuple[str, str]:
    # Lookback bank hajmidan kichik bo'lmasligi kerak — aks holda tanlov
    # doim bank BOSHIDAGI yozuvlarga tarafkashlik qilib, oxirgi
    # yozuvlarga hech qachon yetib bormas edi (masalan 35 ta yozuvli
    # bank + 30 kunlik oyna: 31-yozuv hech qachon tanlanmay qolardi).
    # Kattaroq oyna "oxirgi N kunda takrorlanmasin" talabini yumshatmaydi
    # (aksincha yanada qat'iyroq) — faqat butun bank aylanib chiqishini
    # kafolatlaydi. Standart 90 kunlik oyna — "bir xil maslahat 90 kun
    # ichida qaytarilmasin" talabiga mos.
    effective_lookback = max(lookback, len(bank))
    recent_keys_list = saturn_repo.get_recent_content_keys(post_type, limit=effective_lookback)
    recent_keys = set(recent_keys_list)
    previous_category = category_of(recent_keys_list[0]) if recent_keys_list else None

    candidates = [(key, text) for key, text in bank if key not in recent_keys]
    if not candidates:
        # Bank tugagan (hammasi oxirgi ``lookback`` postda ishlatilgan) —
        # xabar yuborish hech qachon to'xtamasligi kerak, shuning uchun
        # butun bank qayta ochiladi.
        candidates = bank

    # Kecha (oxirgi post)dan boshqa mavzu (kategoriya) tanlashga
    # harakat qilamiz — bir xil mavzu ketma-ket kunlarda takrorlanmasin.
    for key, text in candidates:
        if previous_category is None or category_of(key) != previous_category:
            return key, text

    # Qolgan barcha nomzodlar ham kechagi kategoriyada bo'lsa (masalan
    # bank deyarli tugagan holatda) — baribir yuborish to'xtamaydi.
    return candidates[0]


async def _ai_rephrase(client: AsyncOpenAI, original_text: str, tone_hint: str) -> str:
    try:
        response = await client.responses.create(
            model=_MODEL,
            instructions=(
                f"Sen Saturn kompaniyasi uchun {tone_hint} qisqa maslahat matnini BOSHQACHA "
                "so'zlar bilan qayta yoz. MA'NOSINI o'zgartirma, yangi mavzu qo'shma, uzunligini "
                "oshirma (120 belgidan oshmasin, bitta qisqa jumla). O'zbek tilida yoz. Tibbiy, "
                "huquqiy, siyosiy yoki bahsli mazmun QO'SHMA. Faqat qayta yozilgan matnni qaytar, "
                "boshqa hech narsa yozma."
            ),
            input=original_text,
        )
        return (response.output_text or "").strip()
    except Exception as error:
        logger.warning("OpenAI xatosi (saturn_content rephrase): %r", error)
        return ""


async def pick_morning_advice(client: AsyncOpenAI | None) -> tuple[str, str]:
    """``(bank_key, matn)`` qaytaradi — avval bankdan (oxirgi 30 kunda
    ishlatilmagan mavzu) tanlanadi, so'ng (AI mavjud bo'lsa) xilma-xillik
    uchun qayta ifodalanadi. AI natijasi yaroqsiz bo'lsa yoki AI
    ishlamasa, original bank matni ishlatiladi. ``bank_key`` HAR DOIM
    original mavzu kaliti — takrorlanishni oldini olish shu kalit
    bo'yicha ishlaydi, matn AI tomonidan qayta ifodalangan bo'lsa ham.
    """
    key, original = _pick_from_bank(MORNING_ADVICE_BANK, "morning_advice", morning_category_of)
    if client is None:
        return key, original

    rephrased = await _ai_rephrase(client, original, "ertalabki, ishga oid")
    return key, (rephrased if is_valid_advice(rephrased) else original)


async def pick_night_advice(client: AsyncOpenAI | None) -> tuple[str, str]:
    """``pick_morning_advice`` bilan bir xil mantiq, tungi bank uchun."""
    key, original = _pick_from_bank(NIGHT_ADVICE_BANK, "night_advice", night_category_of)
    if client is None:
        return key, original

    rephrased = await _ai_rephrase(client, original, "kechqurungi, dam olish/tayyorgarlikka oid")
    return key, (rephrased if is_valid_advice(rephrased) else original)
