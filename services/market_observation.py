"""Ta'minotchi bozor razvedkasi — bugungi topilmalarni yozib borish va
narx tarixini taqqoslash uchun.
"""

from repositories import market as market_repo


def log_observation(
    employee_id: int,
    observation_date: str,
    product: str,
    variety: str | None = None,
    photo_reference: str | None = None,
    wholesale_price: str | None = None,
    supplier_seller: str | None = None,
    origin: str | None = None,
    quality: str | None = None,
    minimum_batch: str | None = None,
    notes: str | None = None,
) -> int:
    return market_repo.create_observation(
        employee_id=employee_id,
        observation_date=observation_date,
        product=product,
        variety=variety,
        photo_reference=photo_reference,
        wholesale_price=wholesale_price,
        supplier_seller=supplier_seller,
        origin=origin,
        quality=quality,
        minimum_batch=minimum_batch,
        notes=notes,
    )


def recent_observations(limit: int = 20) -> list[dict]:
    return market_repo.list_recent(limit)


def price_trend(product: str) -> list[dict]:
    return market_repo.get_price_history(product)
