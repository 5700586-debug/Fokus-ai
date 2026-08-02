"""
Fokus AI
Warehouse AI Agent

Vazifalari:
- Ombor qoldig'ini nazorat qilish
- Haftalik hisobotlarni solishtirish
- Tannarx o'zgarishini aniqlash
- Ustama kamayishini nazorat qilish
- Noto'g'ri prixod haqida ogohlantirish
- Farqlarni rahbarga hisobot qilish
"""

class WarehouseAI:

    def analyze(
        self,
        old_stock,
        new_products,
        expenses,
        computer_stock,
        old_margin,
        new_margin
    ):

        expected_stock = old_stock + new_products - expenses

        print("========== OMBOR AI ==========")
        print(f"O'tgan hafta: {old_stock:,}")
        print(f"Kirim: {new_products:,}")
        print(f"Chiqim: {expenses:,}")
        print(f"Hisoblangan qoldiq: {expected_stock:,}")
        print(f"Kompyuter qoldig'i: {computer_stock:,}")

        difference = computer_stock - expected_stock

        if difference != 0:
            print(f"⚠️ Farq aniqlandi: {difference:,}")

        if new_margin < old_margin:
            print("⚠️ Ustama kamaygan.")
            print("Sababini prixodchidan so'rang.")

        if expected_stock > computer_stock:
            print("⚠️ Omborda kamomad bo'lishi mumkin.")

        if expected_stock < computer_stock:
            print("⚠️ Noto'g'ri prixod yoki ortiqcha qoldiq mavjud.")

        print("================================")