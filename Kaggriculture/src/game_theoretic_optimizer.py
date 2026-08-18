"""
Cournot-Nash Best-Response Optimizer for Kaggriculture.
Calculates dynamic crop quotas and market front-running liquidation orders
given real-time market states and opponent supply forecasts.
"""

import math
from src.opponent_tracker import OpponentTracker

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]
PRICE_FLOOR = 1
MARKET_I0 = 10000

MARKET_PARAMS = {
    "WHEAT": {"base": 25, "I0": 10000, "T": 400, "below_func": "sqrt", "below_target": 0.8, "above_func": "log", "above_target": 0.2},
    "CARROT": {"base": 35, "I0": 10000, "T": 450, "below_func": "hinge", "below_target": 1.0, "above_func": "sqrt", "above_target": 0.7},
    "TOMATO": {"base": 60, "I0": 10000, "T": 200, "below_func": "hinge", "below_target": 0.4, "above_func": "sqrt", "above_target": 0.6},
    "STRAWBERRY": {"base": 120, "I0": 10000, "T": 100, "below_func": "sqrt", "below_target": 0.7, "above_func": "linear", "above_target": 1.6},
    "MELON": {"base": 250, "I0": 10000, "T": 300, "below_func": "log", "below_target": 0.2, "above_func": "sq", "above_target": 3.6},
    "EGG": {"base": 50, "I0": 10000, "T": 332, "below_func": "hinge", "below_target": 0.4, "above_func": "log", "above_target": 0.2},
    "MILK": {"base": 160, "I0": 10000, "T": 122, "below_func": "sqrt", "below_target": 0.6, "above_func": "linear", "above_target": 1.6},
    "WOOL": {"base": 200, "I0": 10000, "T": 105, "below_func": "log", "below_target": 0.2, "above_func": "sq", "above_target": 3.2},
    "FERTILIZER": {"base": 100, "I0": 10000, "T": 200, "below_func": "linear", "below_target": 0.4, "above_func": "linear", "above_target": 0.4},
}


def shape_func(name: str, x: float, T: float) -> float:
    if x <= 0: return 0.0
    if name == "linear": return float(x)
    elif name == "sq": return float(x * x)
    elif name == "sqrt": return math.sqrt(float(x))
    elif name == "log": return math.log(1.0 + float(x))
    elif name == "log10": return math.log10(1.0 + float(x))
    elif name == "hinge":
        u = float(x) / float(T) if T > 0 else 0.0
        extra = max(0.0, u - 1.0)
        return u + 8.0 * (extra * extra)
    return float(x)


def get_expected_price(product: str, current_inv: int, additional_units: int = 0) -> int:
    params = MARKET_PARAMS.get(product)
    if not params: return 1
    base = params["base"]
    I0 = params.get("I0", MARKET_I0)
    T = params["T"]
    eff_inv = current_inv + additional_units
    if eff_inv == I0: return base
    if eff_inv < I0:
        f_T = shape_func(params["below_func"], T, T)
        amp = (params["below_target"] * base) / f_T if f_T > 0 else 0.0
        return max(PRICE_FLOOR, round(base + amp * shape_func(params["below_func"], I0 - eff_inv, T)))
    else:
        f_T = shape_func(params["above_func"], T, T)
        amp = (params["above_target"] * base) / f_T if f_T > 0 else 0.0
        return max(PRICE_FLOOR, round(base - amp * shape_func(params["above_func"], eff_inv - I0, T)))


class CournotNashOptimizer:
    def __init__(self, tracker: OpponentTracker):
        self.tracker = tracker

    def select_best_response_crop(
        self,
        pos: tuple[int, int],
        quadrant: str,
        day: int,
        remaining_days: int,
        market_inv: dict,
        nw_wheat_tiles: set,
    ) -> str | None:
        if day == 28: return "WHEAT"
        if day >= 29 or (day >= 26 and day != 28) or remaining_days <= 1: return None

        x, y = pos
        archetype = self.tracker.archetype
        opp_melon_threat = self.tracker.get_projected_supply_in_window("MELON", day, min(30, day + 12))

        # Plot 1 (NW)
        if quadrant == "NW":
            if pos in nw_wheat_tiles: return "WHEAT"
            if day <= 10:
                if archetype == "MONO_MELON" and opp_melon_threat >= 35:
                    return "STRAWBERRY"
                return "MELON"
            elif day <= 25:
                return "STRAWBERRY"
            return "WHEAT"

        # Plot 2 (NE): High Yield Plot
        if quadrant == "NE":
            if day <= 19 and remaining_days >= 10:
                if archetype == "MONO_MELON" and opp_melon_threat >= 35:
                    if (x + y) % 2 == 0: return "TOMATO"
                    return "STRAWBERRY"
                else:
                    if (x + y) % 4 != 0: return "MELON"
                    return "WHEAT"
            return "WHEAT"

        # Plot 3 (SW)
        if quadrant == "SW":
            if day <= 15 and remaining_days >= 10:
                if archetype == "MONO_MELON" and opp_melon_threat >= 35:
                    return "CARROT" if (x + y) % 2 == 0 else "TOMATO"
                if (x + y) % 3 == 0: return "MELON"
                return "WHEAT"
            return "WHEAT"

        # Plot 4 (SE)
        if quadrant == "SE":
            return "WHEAT"

        return "WHEAT"

    def compute_safe_liquidation(
        self,
        product: str,
        qty_in_shed: int,
        market_inv: dict,
        day: int,
        step: int,
        remaining_days: int,
    ) -> int:
        if qty_in_shed <= 0: return 0
        if remaining_days <= 2: return qty_in_shed
        if product in ("WHEAT", "EGG"): return min(qty_in_shed, 20)

        cur_inv = market_inv.get(product, 10000)
        opp_dumps_soon = self.tracker.get_projected_supply_in_window(product, day, day + 1)
        params = MARKET_PARAMS.get(product, {})
        base = params.get("base", 1)
        min_price = max(PRICE_FLOOR, int(base * 0.5))

        # Front-Running: If opponent is about to dump this product in <= 24 steps, liquidate now!
        if opp_dumps_soon >= 10 and qty_in_shed > 0:
            return min(qty_in_shed, 15)

        # Normal Safe Pricing
        safe_q = 0
        test_inv = cur_inv
        for _ in range(min(qty_in_shed, 15)):
            p = get_expected_price(product, test_inv)
            if p < min_price: break
            safe_q += 1
            test_inv += 1

        return max(1, safe_q) if safe_q > 0 else (1 if qty_in_shed > 40 else 0)
