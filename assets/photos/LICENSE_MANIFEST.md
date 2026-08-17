# Saturn fotoreal fon katalogi — litsenziya manifesti

Bu fayl `manifest.json`dagi mashina o'qiy oladigan metadata'ning
inson o'qiy oladigan xulosasi. Har bir foto uchun to'liq maydonlar
(manba ID, fotograf, manba URL, litsenziya, litsenziya URL, checksum,
yuklangan sana) `manifest.json`da saqlanadi.

## Manba va tekshirish jarayoni

Barcha 13 foto **Openverse** (https://openverse.org) orqali topildi —
kalitsiz, faqat `license=cc0,pdm` filtri bilan qidirildi (CC0 yoki
Public Domain Mark — ikkalasi ham tijoriy foydalanishga, o'zgartirishga
va atributsiz ishlatishga ruxsat beradi).

**Tekshirish darajasi — ochiq va aniq aytilsin:** har bir foto uchun
Openverse metadata'sidan tashqari, manba sahifasi (`source_url`)
`curl` orqali qayta so'raldi, lekin ko'pchilik manba saytlari
(stocksnap.io, flickr.com) litsenziya matnini JavaScript orqali
renderlaydi — shuning uchun oddiy `curl`+matn qidiruvi orqali to'liq,
ishonchli qayta tasdiqlash imkonsiz bo'ldi (brauzer emulyatsiyasi bu
muhitda mavjud emas). Haqiqiy ishonch asosi:

1. **stocksnap.io manbali fotolar** (7 ta) — bu sayt o'zining butun
   kutubxonasi uchun ochiq, hujjatlashtirilgan CC0 siyosatiga ega
   (barcha yuklangan fotolar CC0). Bitta-bitta sahifani JS orqali
   qayta tekshirish shart emas — sayt darajasidagi siyosat ishonchli.
2. **Flickr manbali fotolar** (5 ta, "pdm" — Public Domain Mark) —
   litsenziya fotografning o'zi Flickr tizimida belgilagan holat,
   Openverse rasman shu maydonni API orqali oladi (qo'lda kiritilgan
   emas).
3. **rawpixel/Wikimedia manbali fotolar** (2 ta, CC0) — rawpixel ham
   faqat public-domain/CC0 arxiv materiallarini nashr qiladi.

Bu **"Openverse metadata'siga ko'r-ko'rona ishonish emas"** — manba
turi va uning siyosati aniq tekshirilgan — lekin **har bir alohida
sahifani qo'lda, brauzerda ochib qayta tasdiqlash ham emas**. Agar
loyiha egasi yanada qat'iyroq tekshirish (masalan real brauzer bilan
skrinshot) xohlasa, bu keyingi qadam sifatida qo'shilishi mumkin.

## Foydalanish

- Telegram xabarida (agar bu foto ishlatilsa) caption oxiriga qisqa
  kredit qo'shiladi: `📷 {fotograf} / {manba}`.
- Fayllar hech qachon qayta tahrirlanmagan holda saqlanmaydi — faqat
  render vaqtida (crop/rang/ob-havo effekti) vaqtinchalik xotirada
  o'zgartiriladi, asl fayl `assets/photos/originals/`da o'zgarishsiz
  qoladi.
- Checksum (`checksum_sha256`) fayl mazmuni tasodifan yoki
  qasddan o'zgartirilganini aniqlash uchun — mos kelmasa
  (`services/photo_catalog.py`), o'sha yozuv katalogdan avtomatik
  chiqarib tashlanadi.

## Kataloglangan fotolar (13 ta, 12 talab qilingan kategoriyani qamrab oladi)

| photo_id | fasl | ob-havo | vaqt | fotograf | litsenziya |
|---|---|---|---|---|---|
| spring_meadow_oregon | bahor | clear | morning | Bonnie Moreland | PDM |
| spring_rain_buds | bahor | rain | morning | Wonderlane | CC0 |
| summer_meadow | yoz | clear | morning | eberhard grossgasteiger | CC0 |
| desert_dunes | yoz | hot | morning | Burst | CC0 |
| autumn_golden_leaves | kuz | season_default | morning | Free Nature Stock | CC0 |
| autumn_forest_rain | kuz | rain | morning | azxa661 | PDM |
| windy_wheat_field | barcha | windy | morning | Noma'lum (Wikimedia) | CC0 |
| winter_snow_river | qish | snow | morning | Bonnie Moreland | PDM |
| foggy_coast | barcha | fog | morning | Bonnie Moreland | PDM |
| thunderstorm_joshua_tree | barcha | thunderstorm | morning | National Park Service | CC0 |
| night_moon_trees | barcha | clear | night | Brandon Morgan | CC0 |
| crescent_moon | barcha | clear | night | Stephen Rahn | CC0 |
| rainy_night_street | barcha | rain | night | Terry Kearney | CC0 |

**Muhim: bu 13 ta — 60-100 ta maqsaddan ANCHA kam.** Har bir foto
qo'lda ko'zdan kechirilib (odam yuzi, o'qiladigan reklama/logotip,
sun'iy/AI-generatsiya belgilari yo'qligi tekshirilib) tanlangani
uchun, ko'proq foto qo'shish alohida, davom etadigan curation ishi
talab qiladi. Qarang loyiha ildizidagi yakuniy hisobotdagi
`PHOTO_SOURCE_REQUIRED` bo'limi.

## Rad etilgan nomzodlar (nima uchun ishlatilmadi)

Curation jarayonida quyidagilar ko'rib chiqilib, RAD ETILDI:

- Openverse'da "pdm"/"cc0" deb belgilangan, lekin sarlavhasi aniq
  **AI-generatsiya prompt** ko'rinishidagi ("A photo of a shiny black
  Porsche driving through a rainy wet city...") bir nechta "natija" —
  bular HAQIQIY fotosurat emas, sun'iy generatsiya, shuning uchun
  butunlay chetlab o'tildi (talab: faqat haqiqiy fotografik rasmlar).
- Odam yuzi/tanib bo'ladigan odam ko'rinadigan bir nechta nomzod
  (masalan oilaviy sayr fotosi) — rad etildi.
- Juda "vahimali"/falokat ko'rinishidagi bitta kuchli chaqmoq fotosi
  (shahar ustida ulkan chaqmoq) — o'rniga yumshoqroq, uzoqdan
  ko'rinuvchi, iliq tusli chaqmoq fotosi tanlandi.
