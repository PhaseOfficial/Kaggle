"""Market pricing formulas, price elasticity model, and order slicing engine."""

import math
from src.constants import MARKET_PARAMS, MARKET_I0, PRICE_FLOOR, SHOPS, SINGLE_PRODUCT_SHOPS


def shape_func(name: str, x: float, T: float) -> float:
    """Evaluates the piecewise shape function for market pricing."""
    if x <= 0:
        return 0.0
    if name == "linear":
        return float(x)
    elif name == "sq":
        return float(x * x)
    elif name == "sqrt":
        return math.sqrt(float(x))
    elif name == "log":
        return math.log(1.0 + float(x))
    elif name == "log10":
        return math.log10(1.0 + float(x))
    elif name == "hinge":
        u = float(x) / float(T) if T > 0 else 0.0
        extra = max(0.0, u - 1.0)
        return u + 8.0 * (extra * extra)
    return float(x)


def get_price(product: str, inv: int, market_params: dict = None) -> int:
    """Computes the exact market price for a product given market inventory."""
    params = (market_params or MARKET_PARAMS).get(product)
    if not params:
        return 1

    base = params["base"]
    I0 = params.get("I0", MARKET_I0)
    T = params["T"]

    if inv == I0:
        return base

    if inv < I0:
        # Scarcity: price goes up
        func_name = params["below_func"]
        target = params["below_target"]
        delta = I0 - inv
        f_T = shape_func(func_name, T, T)
        amp = (target * base) / f_T if f_T > 0 else 0.0
        f_val = shape_func(func_name, delta, T)
        raw_price = base + amp * f_val
    else:
        # Glut: price goes down
        func_name = params["above_func"]
        target = params["above_target"]
        delta = inv - I0
        f_T = shape_func(func_name, T, T)
        amp = (target * base) / f_T if f_T > 0 else 0.0
        f_val = shape_func(func_name, delta, T)
        raw_price = base - amp * f_val

    return max(PRICE_FLOOR, round(raw_price))


def get_total_sale_revenue(product: str, current_inv: int, quantity: int, market_params: dict = None) -> tuple[int, int]:
    """
    Computes total revenue and end price when selling `quantity` units one by one.
    Returns: (total_revenue, final_price)
    """
    total_rev = 0
    inv = current_inv
    for _ in range(quantity):
        p = get_price(product, inv, market_params)
        total_rev += p
        if p > PRICE_FLOOR:
            inv += 1
    return total_rev, get_price(product, inv, market_params)


def calculate_shop_drain_rate(unlocked_shops: list[str]) -> dict[str, float]:
    """
    Calculates daily consumption rate by town shops for each product.
    Town center consumes 1 of each per day (24 turns).
    Each shop consumes 1 per 4 turns (6 per day), or 12 per day for single-product shops.
    """
    daily_drain = {}
    for shop in unlocked_shops:
        products = SHOPS.get(shop, [])
        is_single = shop in SINGLE_PRODUCT_SHOPS
        rate = 12.0 if is_single else 6.0
        for p in products:
            daily_drain[p] = daily_drain.get(p, 0.0) + rate
    return daily_drain


def get_safe_sell_quantity(
    product: str,
    current_inv: int,
    available_in_shed: int,
    unlocked_shops: list[str],
    remaining_days: int,
    min_acceptable_price_ratio: float = 0.5,
) -> int:
    """
    Calculates the optimal sell quantity for this turn that will not crash price below acceptable threshold.
    """
    if available_in_shed <= 0:
        return 0

    params = MARKET_PARAMS.get(product, {})
    base = params.get("base", 1)
    min_price = max(PRICE_FLOOR, int(base * min_acceptable_price_ratio))

    # If already near end of season (days remaining <= 2), liquidate aggressively
    if remaining_days <= 2:
        return min(available_in_shed, 100)

    # For glut-resistant staples (WHEAT, EGG), can sell more freely
    if product in ("WHEAT", "EGG"):
        return min(available_in_shed, 20)

    # For sensitive goods, check how many units we can sell before price drops below min_price
    safe_q = 0
    test_inv = current_inv
    for _ in range(min(available_in_shed, 15)):
        p = get_price(product, test_inv)
        if p < min_price:
            break
        safe_q += 1
        test_inv += 1

    return max(1, safe_q) if safe_q > 0 else (1 if available_in_shed > 50 else 0)
