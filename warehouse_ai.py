class WarehouseAI:
    def analyze(
        self,
        old_stock,
        new_products,
        expenses,
        computer_stock,
        old_margin,
        new_margin,
    ):
        expected_stock = old_stock + new_products - expenses
        difference = computer_stock - expected_stock

        result = []

        if expected_stock > computer_stock:
            result.append("⚠️ Omborda kamomad bo‘lishi mumkin.")

        if expected_stock < computer_stock:
            result.append("⚠️ Noto‘g‘ri prixod yoki ortiqcha qoldiq mavjud.")

        if difference != 0:
            result.append(
                f"⚠️ Omborda {difference:,} so‘m farq aniqlandi."
            )
        else:
            result.append("✅ Ombor hisoboti to‘g‘ri.")

        if new_margin < old_margin:
            result.append("⚠️ Ustama kamaygan.")
            result.append("Sababini prixodchidan so‘rang.")

        return "\n".join(result)