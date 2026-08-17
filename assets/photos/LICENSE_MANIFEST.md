# Saturn fotoreal fon katalogi — litsenziya manifesti

Bu fayl `manifest.json`dagi mashina o'qiy oladigan metadata'ning inson o'qiy oladigan xulosasi. Har bir foto uchun to'liq maydonlar (manba ID, fotograf, manba URL, litsenziya, litsenziya URL, checksum, yuklangan sana) `manifest.json`da saqlanadi.

## Umumiy son: 123 ta haqiqiy fotosurat

Manba bo'yicha taqsimot:

- **Pexels**: 58 ta
- **Wikimedia Commons**: 52 ta
- **openverse**: 13 ta

Litsenziya bo'yicha taqsimot:

- **Pexels License**: 58 ta
- **Public Domain Mark**: 40 ta
- **CC0 (Public Domain)**: 25 ta

## Manba va tekshirish jarayoni

**1. Wikimedia Commons** (https://commons.wikimedia.org) — kalitsiz rasmiy API orqali qidirildi (`action=query&generator=search`, `prop=imageinfo&iiprop=extmetadata`). Litsenziya bu yerda **Openverse orqali emas, Commons'ning o'z API'sidan to'g'ridan-to'g'ri** olindi — `extmetadata.LicenseShortName` maydoni Commons fayl sahifasining o'zidagi strukturaviy shablon ma'lumoti (fayl sahifasini brauzerda ochib ko'rish bilan bir xil manba, faqat API orqali). Faqat `LicenseShortName` aniq "CC0 1.0" yoki "Public Domain" bo'lgan va `Restrictions` maydoni bo'sh bo'lgan fayllar qabul qilindi. Sarlavha bo'yicha filtr AI-generatsiya/multfilm/xarita/hujjat/logotip/portret so'zlarini chetlab o'tdi — lekin YAKUNIY qabul har bir nomzodni kichik rasm (thumbnail) to'plamida ko'zdan kechirib chiqarildi (odam yuzi, brend/matn, sun'iy/AI ko'rinish yo'qligi tasdiqlandi).

**2. Pexels** (https://www.pexels.com/api/documentation/) — foydalanuvchi tomonidan ta'minlangan `PEXELS_API_KEY` bilan (faqat `.env` orqali, kodga/logga/testga yozilmagan). Pexels litsenziyasi (https://www.pexels.com/license/) haqiqiy, rasmiy va bir xil barcha fotolar uchun — CC0/Public Domain EMAS, lekin tijoriy va shaxsiy foydalanishga to'liq ruxsat beruvchi alohida ochiq litsenziya (atributsiz ishlatish mumkin, lekin loyiha konventsiyasiga ko'ra baribir fotograf krediti saqlanadi).

**Muhim aniqlik:** foydalanuvchi so'rovi "faqat CC0 yoki Public Domain" deb boshlangan edi; keyinroq foydalanuvchi Pexels'ni **qo'shimcha, aniq belgilangan manba** sifatida faollashtirishni so'radi. Shu sabab quyidagi jadvalda har bir fotoning haqiqiy litsenziyasi (`cc0` / `pdm` / `pexels`) alohida ko'rsatilgan — Pexels-manbali fotolar CC0/PDM deb noto'g'ri belgilanmagan.

**Rad etilgan nomzodlar:** curation davomida quyidagilar rad etildi — AI-generatsiya "foto"lar (sarlavhasi aniq prompt ko'rinishidagi), chizilgan/multfilm/vektor rasmlar, skanerlangan hujjatlar/eski reklama sahifalari, xarita/sun'iy yo'ldosh mavhum tasvirlari, odam yuzi/tanib bo'ladigan shaxs aniq ko'rinadigan kadrlar, harbiy texnika, va haddan tashqari vahimali/falokat ko'rinishidagi tabiat hodisalari (masalan juda yaqin/kuchli chaqmoq — o'rniga uzoqroq, iliq tusli, estetik chaqmoq tanlandi).

## Variant matematikasi (haqiqiy, to'qib chiqarilmagan)

Har bir asosiy fotodan `VARIANTS_PER_PHOTO = 72` ta ko'z bilan farqlanadigan variant olinadi (zoom darajasi x mirror x pan joylashuvi x yorug'lik/rang ohangi kombinatsiyasi — qarang `services/photo_catalog.py` va `services/photo_scene.py`dagi izoh). Jami: **123 foto x 72 variant = 8856 ta haqiqiy, deterministik kombinatsiya** (tong+tun kategoriyalari birgalikda hisoblanganda). Bu `services/photo_catalog.total_real_variant_count()` funksiyasi orqali dasturiy ravishda tekshiriladi.

## Fasl/ob-havo/vaqt kategoriyalari bo'yicha qamrov

| fasl | ob-havo | vaqt | foto soni |
|---|---|---|---|
| bahor | clear | morning | 15 |
| bahor | rain | morning | 4 |
| barcha (universal) | clear | night | 7 |
| barcha (universal) | fog | morning | 8 |
| barcha (universal) | rain | night | 9 |
| barcha (universal) | thunderstorm | morning | 6 |
| barcha (universal) | windy | morning | 13 |
| kuz | rain | morning | 4 |
| kuz | season_default | morning | 9 |
| qish | clear | morning | 8 |
| qish | snow | morning | 7 |
| qish | snow | night | 7 |
| yoz | clear | morning | 16 |
| yoz | hot | morning | 9 |
| yoz | season_default | morning | 1 |

Barcha 3 avvalgi "vektor-fallback" bo'shlig'i (qish+ochiq+tong, qish+qorli+tun, yoz uchun umumiy ob-havo-standart) endi haqiqiy fotolar bilan qoplangan.

## To'liq ro'yxat

| photo_id | fasl | ob-havo | vaqt | manba | fotograf | litsenziya |
|---|---|---|---|---|---|---|
| px_spring_blossom_blue_sky | bahor | clear | morning | Pexels | WENCHENG JIANG | pexels |
| px_spring_blossom_pink_branches | bahor | clear | morning | Pexels | Studio Naae | pexels |
| px_spring_blossom_tree_field | bahor | clear | morning | Pexels | laura dominguez | pexels |
| px_spring_blossom_warm_light | bahor | clear | morning | Pexels | Pixabay | pexels |
| px_spring_buttercup_meadow | bahor | clear | morning | Pexels | Nikolaeva Nastia | pexels |
| px_spring_pink_field_wide | bahor | clear | morning | Pexels | Lany-Jade Mondou | pexels |
| px_spring_pink_wildflowers_meadow | bahor | clear | morning | Pexels | عبد سالم | pexels |
| px_spring_poppy_bokeh | bahor | clear | morning | Pexels | Ad Hartjes | pexels |
| px_spring_white_daisies_closeup | bahor | clear | morning | Pexels | Stanislav Kondratiev | pexels |
| px_spring_yellow_rapeseed_field | bahor | clear | morning | Pexels | zhu yi | pexels |
| spring_daisy_grass | bahor | clear | morning | Commons | Fatjon Aliraj | cc0 |
| spring_field_road | bahor | clear | morning | Commons | Fons Heijnsbroek | cc0 |
| spring_meadow_oregon | bahor | clear | morning | openverse | Bonnie Moreland (free images) | pdm |
| spring_plowed_field_flowers | bahor | clear | morning | Commons | Fons Heijnsbroek | cc0 |
| spring_poppy_field | bahor | clear | morning | Commons | USDA NRCS Texas | pdm |
| spring_crocus_rain | bahor | rain | morning | Commons | Cbaile19 | cc0 |
| spring_forest_waterfall | bahor | rain | morning | Commons | BLM Oregon & Washington | pdm |
| spring_garden_pavilion | bahor | rain | morning | Commons | Daderot | cc0 |
| spring_rain_buds | bahor | rain | morning | openverse | Wonderlane | cc0 |
| crescent_moon | barcha | clear | night | openverse | Stephen Rahn | cc0 |
| night_bay_lights | barcha | clear | night | Commons | W.carter | cc0 |
| night_bay_moon_dusk | barcha | clear | night | Commons | W.carter | cc0 |
| night_bay_streak_light | barcha | clear | night | Commons | W.carter | cc0 |
| night_moon_trees | barcha | clear | night | openverse | Brandon Morgan | cc0 |
| night_saguaro_moon | barcha | clear | night | Commons | SaguaroNPS | pdm |
| px_lake_pier_startrails_night | barcha | clear | night | Pexels | cristian rossa | pexels |
| fog_autumn_lake | barcha | fog | morning | Commons | USFWS Mountain Prairie | pdm |
| fog_forest_path | barcha | fog | morning | Commons | Alessio Lin lin_alessio | cc0 |
| fog_lake_glow_trees | barcha | fog | morning | Commons | USFWS Mountain Prairie | pdm |
| fog_lake_sun_glow | barcha | fog | morning | Commons | USFWS Mountain Prairie | pdm |
| fog_pier_sun | barcha | fog | morning | Commons | USFWS Mountain Prairie | pdm |
| fog_pine_hillside | barcha | fog | morning | Commons | Jon Flobrant jonflobrant | cc0 |
| fog_stream_path | barcha | fog | morning | Commons | Alex Iby ibydesigns | cc0 |
| foggy_coast | barcha | fog | morning | openverse | Bonnie Moreland (free images) | pdm |
| night_rain_old_town_alley | barcha | rain | night | Commons | Nils Söderman | cc0 |
| night_rain_streetlight_branches | barcha | rain | night | Commons | Me Nit | pdm |
| px_rain_alley_lanterns_empty | barcha | rain | night | Pexels | Nils Rotura | pexels |
| px_rain_colorful_reflection | barcha | rain | night | Pexels | Jerry Zhang | pexels |
| px_rain_light_bokeh_abstract | barcha | rain | night | Pexels | Serge Cyneat | pexels |
| px_rain_narrow_alley_lights | barcha | rain | night | Pexels | Nils Rotura | pexels |
| px_rain_street_corner_lights | barcha | rain | night | Pexels | Nils Rotura | pexels |
| px_rain_window_droplets_bokeh | barcha | rain | night | Pexels | Nathan Tran | pexels |
| rainy_night_street | barcha | rain | night | openverse | Terry Kearney | cc0 |
| storm_agave_hills | barcha | thunderstorm | morning | Commons | NPS Photo | pdm |
| storm_coastal_waves | barcha | thunderstorm | morning | Commons | Bonnie Moreland from Oregon, United States | pdm |
| storm_lightning_pink_trees | barcha | thunderstorm | morning | Commons | evergladesnps | pdm |
| storm_lightning_saguaro | barcha | thunderstorm | morning | Commons | SaguaroNPS | pdm |
| storm_pink_mountain | barcha | thunderstorm | morning | Commons | Bob Wick; Bureau  of Land Management | pdm |
| thunderstorm_joshua_tree | barcha | thunderstorm | morning | openverse | National Park Service | cc0 |
| px_windy_aerial_curved_road | barcha | windy | morning | Pexels | Niklas Jeromin | pexels |
| px_windy_golden_field_dusk | barcha | windy | morning | Pexels | Leandro Pita | pexels |
| px_windy_golden_grass_closeup | barcha | windy | morning | Pexels | Elisabeth Ende | pexels |
| px_windy_golden_horizon | barcha | windy | morning | Pexels | Julia Fuchs | pexels |
| px_windy_grass_dusk_silhouette | barcha | windy | morning | Pexels | Nikolaeva Nastia | pexels |
| px_windy_grass_pink_clouds | barcha | windy | morning | Pexels | Kevyn Costa | pexels |
| px_windy_green_hills_wheat | barcha | windy | morning | Pexels | ebru ün | pexels |
| px_windy_pink_flowers_blur | barcha | windy | morning | Pexels | Nguyen Ngoc Tien | pexels |
| px_windy_pink_reeds_blur | barcha | windy | morning | Pexels | Nguyen Ngoc Tien | pexels |
| px_windy_reeds_hills | barcha | windy | morning | Pexels | _ Whittington | pexels |
| windy_dune_grass | barcha | windy | morning | Commons | NPS | pdm |
| windy_wheat_closeup | barcha | windy | morning | Commons | W.carter | cc0 |
| windy_wheat_field | barcha | windy | morning | openverse | Noma'lum (Wikimedia orqali, rawpixel manbasi) | cc0 |
| autumn_forest_rain | kuz | rain | morning | openverse | azxa661 | pdm |
| autumn_leaf_water_reflection | kuz | rain | morning | Commons | W.carter | cc0 |
| autumn_rain_avenue_path | kuz | rain | morning | Commons | Aleksandr Gorlov | pdm |
| autumn_wet_leaves_rocks | kuz | rain | morning | Commons | Nick Holden from England | pdm |
| autumn_aspen_blue_sky | kuz | season_default | morning | Commons | Intermountain Region US Forest Service | pdm |
| autumn_aspen_dark | kuz | season_default | morning | Commons | Intermountain Region US Forest Service | pdm |
| autumn_golden_leaves | kuz | season_default | morning | openverse | Free Nature Stock | cc0 |
| autumn_larch_fence | kuz | season_default | morning | Commons | Intermountain Region US Forest Service | pdm |
| autumn_larch_road | kuz | season_default | morning | Commons | Forest Service - Northern Region | pdm |
| autumn_river_bend | kuz | season_default | morning | Commons | Heuer Ted, U.S. Fish and Wildlife Service | pdm |
| autumn_tundra_mountain | kuz | season_default | morning | Commons | USFWSAlaska | pdm |
| autumn_tundra_stream | kuz | season_default | morning | Commons | USFWSAlaska | pdm |
| autumn_tundra_vast | kuz | season_default | morning | Commons | USFWSAlaska | pdm |
| px_winter_forest_path_blue_sky | qish | clear | morning | Pexels | Samuel Haché | pexels |
| px_winter_frosted_river_trees | qish | clear | morning | Pexels | Curioso Photography | pexels |
| px_winter_park_backlit_tree | qish | clear | morning | Pexels | Дмитрий Зорин | pexels |
| px_winter_snow_dunes_sunset | qish | clear | morning | Pexels | Barnabas Davoti | pexels |
| px_winter_sunny_forest_rays | qish | clear | morning | Pexels | Baskin Creative Co. | pexels |
| winter_frosty_hilltop_sun | qish | clear | morning | Commons | ShenandoahNPS | pdm |
| winter_frozen_lake_mountains | qish | clear | morning | Commons | USFWS Mountain Prairie | pdm |
| winter_road_snowy_trees | qish | clear | morning | Commons | ShenandoahNPS | pdm |
| winter_glacier_ridge_pink | qish | snow | morning | Commons | Sam Ferrara samferrara | cc0 |
| winter_peak_clouds | qish | snow | morning | Commons | YellowstoneNPS | pdm |
| winter_pond_lone_tree | qish | snow | morning | Commons | Jacob W. Frank | pdm |
| winter_shasta_pink_sunset | qish | snow | morning | Commons | NPS Photo | pdm |
| winter_snow_river | qish | snow | morning | openverse | Bonnie Moreland (free images) | pdm |
| winter_snowy_peak_forest | qish | snow | morning | Commons | Steve Redman (MORA) | pdm |
| winter_valley_aerial | qish | snow | morning | Commons | Goldmann Jo, U.S. Fish and Wildlife Service | pdm |
| night_snowy_valley_moonlit | qish | snow | night | Commons | Great Sand Dunes National Park and Preserve | pdm |
| px_night_snow_branches_twilight | qish | snow | night | Pexels | Plato Terentev | pexels |
| px_night_snow_foggy_slope | qish | snow | night | Pexels | Rastislav Durica | pexels |
| px_night_snow_forest_twilight | qish | snow | night | Pexels | Nils Jonsson | pexels |
| px_night_snow_horizon_glow | qish | snow | night | Pexels | Barnabas Davoti | pexels |
| px_night_snow_lone_tree_dusk | qish | snow | night | Pexels | Simon Berger | pexels |
| px_night_snow_train_tracks | qish | snow | night | Pexels | Dawid Boldys | pexels |
| px_lake_golden_grass_mountain | yoz | clear | morning | Pexels | Janiere Fernandez | pexels |
| px_lake_green_valley_mountains | yoz | clear | morning | Pexels | Olja Knies | pexels |
| px_lake_peak_reflection | yoz | clear | morning | Pexels | Oskar Gross | pexels |
| px_lake_snowy_mountains_winter | yoz | clear | morning | Pexels | - landsmann - | pexels |
| px_lake_turquoise_bay_cliffs | yoz | clear | morning | Pexels | Elijah Cobb | pexels |
| px_lake_turquoise_clear_sky | yoz | clear | morning | Pexels | THARUN GOWDA | pexels |
| px_summer_field_two_trees | yoz | clear | morning | Pexels | Vitaliy Bratkov | pexels |
| px_summer_golden_backlit_wheat | yoz | clear | morning | Pexels | mauro savoca | pexels |
| px_summer_hay_bale_field | yoz | clear | morning | Pexels | Nikolett Emmert | pexels |
| px_summer_hills_dusk_pink | yoz | clear | morning | Pexels | Nikolett Emmert | pexels |
| px_summer_rolling_green_hills | yoz | clear | morning | Pexels | Nikolett Emmert | pexels |
| px_summer_sunflower_field_wide | yoz | clear | morning | Pexels | MrGajowy3 Teodor | pexels |
| px_summer_wheat_tracks_horizon | yoz | clear | morning | Pexels | Gil Vdr | pexels |
| px_summer_wheat_treeline | yoz | clear | morning | Pexels | Leonid Danilov | pexels |
| summer_meadow | yoz | clear | morning | openverse | eberhard grossgasteiger | cc0 |
| summer_wildflower_meadow | yoz | clear | morning | Commons | Mount Rainier National Park from Ashford, WA, United States | pdm |
| desert_dune_ripples | yoz | hot | morning | Commons | NASA | pdm |
| desert_dunes | yoz | hot | morning | openverse | Burst | cc0 |
| desert_rock_pinnacles | yoz | hot | morning | Commons | mypubliclands | pdm |
| px_desert_deadvlei_trees | yoz | hot | morning | Pexels | Floor November | pexels |
| px_desert_dune_closeup_gold | yoz | hot | morning | Pexels | 光曦 刘 | pexels |
| px_desert_dune_ridges_clouds | yoz | hot | morning | Pexels | Moussa Idrissi | pexels |
| px_desert_fence_posts | yoz | hot | morning | Pexels | Kássia Melo | pexels |
| px_desert_red_canyon_road | yoz | hot | morning | Pexels | György Lakatos | pexels |
| px_desert_ripple_pattern | yoz | hot | morning | Pexels | Dubang chang | pexels |
| summer_dusk_horizon | yoz | season_default | morning | Commons | Unknown authorUnknown author | cc0 |

## Foydalanish

- Telegram xabarida (agar bu foto ishlatilsa) caption oxiriga qisqa kredit qo'shiladi: `📷 {fotograf} / {manba}`.
- Fayllar hech qachon qayta tahrirlanmagan holda saqlanmaydi — faqat render vaqtida (crop/rang/ob-havo effekti) vaqtinchalik xotirada o'zgartiriladi, asl fayl `assets/photos/originals/`da o'zgarishsiz qoladi. (Repo hajmini kichraytirish uchun originallar 2000px uzun tomonga va JPEG sifatiga qisilgan — bu faqat fayl hajmiga ta'sir qiladi, litsenziya yoki muallif ma'lumotiga emas.)
- Checksum (`checksum_sha256`) fayl mazmuni tasodifan yoki qasddan o'zgartirilganini aniqlash uchun — mos kelmasa (`services/photo_catalog.py`), o'sha yozuv katalogdan avtomatik chiqarib tashlanadi.
