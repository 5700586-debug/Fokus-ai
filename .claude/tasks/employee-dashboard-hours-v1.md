# FOKUS AI — Employee dashboard hours wiring V1

## Kontekst

Current feature branch checkpoint: `8b252674ead87b7a2795419ef16b1a852b744081`.

`services/attendance.py`da month-to-date work-hours core allaqachon mavjud:
- `get_month_to_date_hours(...)`
- `get_worked_hours_for_day(...)`
- `record_manual_departure(...)`

`services/employee_dashboard.py` esa hozir `hours: {"label": "Ma'lumot yo'q"}` hardcoded fallback qaytaryapti.

## Maqsad

Faqat mavjud work-hours service natijasini xodimning `/mystars` dashboardiga toza va minimal tarzda ulang.

## Qat’iy cheklovlar

- **Windows / PowerShell / CMD umuman ishlatma.**
- Test/runtime faqat GitHub Actions `ubuntu-latest` muhitida.
- Faqat `feature/hr-conversational-interview` branchida ishlagin.
- `main` va productionga tegma.
- Gemini ishlatma.
- Face ID real integratsiyasini qurma.
- Telegramda yangi command yoki yangi katta flow yaratma.
- Bonus/minus biznes qoidalarini o‘zgartirma.
- Yangi jadval yaratma.
- Noma’lum qiymatni taxmin qilma.

## Vazifa

1. `services/employee_dashboard.py::build_dashboard()` ichidagi hardcoded `hours` fallbackni mavjud `services.attendance.get_month_to_date_hours(...)` natijasi bilan almashtir.

2. `format_dashboard_text()`da oy boshidan soatlar sodda ko‘rinsin:
   - planned_hours mavjud bo‘lsa: `📋 Reja soati: X soat`
   - planned_hours `None` bo‘lsa: `📋 Reja soati: Ma'lumot yo'q`
   - actual_hours mavjud bo‘lsa: `🕒 Ishlangan soat: X soat`
   - actual_hours `None` bo‘lsa: `🕒 Ishlangan soat: Ma'lumot yo'q`

3. Float ko‘rinishini foydalanuvchiga toza chiqar: butun son bo‘lsa `176 soat`, kasr bo‘lsa ortiqcha nol va uzun floating-point dumisiz masalan `87.5 soat`.

4. Existing behavior buzilmasin:
   - profil
   - bonus/minus/net
   - kechagi davomat
   - oxirgi 2 kun
   - photo fallback
   o‘zgarishsiz qolsin.

5. Minimal targeted test yoz yoki mavjud `tests/test_employee_dashboard.py`ni kengaytir:
   - planned + actual mavjud
   - planned `None`
   - actual `None`
   - float format
   - eski dashboard qismlari saqlanganini tekshir.

6. Faqat kerakli targeted testlarni Ubuntu/Linuxda ishga tushir. Katta full-suite audit qilma.

7. Test PASS bo‘lsa implementation/test o‘zgarishlarini oddiy commit qilib shu feature branchga push qil. Force push qilma.

## Arxitektura qarori

Bu vazifada yangi attendance hisob-kitobi yozilmaydi. `employee_dashboard` faqat allaqachon mavjud service natijasini view-modelga olib kiradi. Bu minimal, reversible va duplication yaratmaydigan variant.

## Yakuniy hisobot

Qisqa yoz:
1. nima o‘zgardi
2. targeted test natijasi
3. final commit SHA
4. `main/production: untouched`
