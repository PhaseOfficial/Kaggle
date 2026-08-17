"""Macro-Economic Planner: Strictly Wheat, Melon, and Strawberry after Melon with Fibonacci Hiring."""

from collections import Counter
from src.constants import CROPS, PRODUCTS, LIVESTOCK_PLOTS, NW_WHEAT_TILES
from src.state import FarmState
from src.market_model import get_safe_sell_quantity

FIBONACCI_COSTS = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377]


def get_hire_cost(n: int) -> int:
    """Returns the Fibonacci hiring cost for the n-th hand today (0-indexed)."""
    if n < len(FIBONACCI_COSTS):
        return FIBONACCI_COSTS[n]
    a, b = FIBONACCI_COSTS[-2], FIBONACCI_COSTS[-1]
    for _ in range(n - len(FIBONACCI_COSTS) + 1):
        a, b = b, a + b
    return b


def get_target_crop_for_pos(pos: tuple[int, int], remaining_days: int, day: int) -> str | None:
    # 1. Day 28 Whole-Farm Wheat Blitz (Empty tiles only): 2-day fast turnover harvest on Day 30!
    if day == 28:
        return "WHEAT"

    # Strict Cutoffs
    if day >= 29 or (day >= 26 and day != 28) or remaining_days <= 1:
        return None

    # Plot 1 (NW): x < 5 and y < 5
    if pos[0] < 5 and pos[1] < 5:
        if pos in NW_WHEAT_TILES:
            return "WHEAT"
        if day <= 10:
            return "MELON"
        elif day <= 25:
            return "STRAWBERRY"
        return "WHEAT"

    # Plot 2 (NE): Covers x in [5, 9], y in [0, 4] -> HIGH-YIELD WATERMELON PRODUCTION (Days 0-19)
    if pos[0] >= 5 and pos[1] < 5:
        if day <= 19 and remaining_days >= 10:
            if (pos[0] + pos[1]) % 4 != 0:
                return "MELON"
            return "WHEAT"
        return "WHEAT"

    # Plot 3 (SW): Covers x in [0, 4], y in [5, 9] -> Wheat & Targeted Melons
    if pos[0] < 5 and pos[1] >= 5:
        if day <= 15 and remaining_days >= 10 and (pos[0] + pos[1]) % 3 == 0:
            return "MELON"
        return "WHEAT"

    # Plot 4 (SE): Covers x in [5, 9], y in [5, 9] -> Wheat
    if pos[0] >= 5 and pos[1] >= 5:
        return "WHEAT"

    return "WHEAT"


class ZonalMacroPlanner:
    """Manages full-farm budget, Fibonacci daily hiring, livestock procurement, fertilizer management, and liquidation."""

    def __init__(self, state: FarmState):
        self.state = state

    def plan_market_orders(self) -> list:
        orders = []
        max_orders = 10
        money = self.state.money
        day = self.state.day
        rem_days = self.state.remaining_days
        num_quads = len(self.state.unlocked_quadrants)

        # -------------------------------------------------------------
        # 1. FIBONACCI DYNAMIC WORKFORCE HIRING
        # -------------------------------------------------------------
        base_hires = 5 if num_quads == 1 else (7 if num_quads == 2 else 9)
        harvestable_count = len(self.state.get_harvestable_tiles())

        if harvestable_count >= 15 and money >= 1000:
            base_hires = min(base_hires + 1, 10)
        if harvestable_count >= 25 and money >= 3000:
            base_hires = min(base_hires + 1, 11)

        if day <= 3:
            base_hires = min(base_hires, 5)
        elif money < 300:
            base_hires = min(base_hires, 5)

        current_hires = self.state.hires_today
        while current_hires < base_hires and len(orders) < max_orders:
            cost = get_hire_cost(current_hires)
            reserve = 200 if day < 26 else 0
            if money >= cost and (money - cost) >= reserve:
                orders.append(["HIRE"])
                money -= cost
                current_hires += 1
            else:
                break

        # -------------------------------------------------------------
        # 2. LIVESTOCK PROCUREMENT
        # -------------------------------------------------------------
        target_cows = 2
        target_sheep = 2

        total_cows_held = sum(1 for p, info in LIVESTOCK_PLOTS["NW"].items() if info[1] == "COW" and isinstance(self.state.get_tile(*p), dict) and self.state.get_tile(*p).get("animal") == "COW") + self.state.shed.get("COW", 0) + sum(inv.get("COW", 0) for inv in self.state.inventories)
        total_sheep_held = sum(1 for p, info in LIVESTOCK_PLOTS["NW"].items() if info[1] == "SHEEP" and isinstance(self.state.get_tile(*p), dict) and self.state.get_tile(*p).get("animal") == "SHEEP") + self.state.shed.get("SHEEP", 0) + sum(inv.get("SHEEP", 0) for inv in self.state.inventories)

        if (day >= 1 or self.state.shed.get("WHEAT", 0) >= 3) and day <= 20 and len(orders) < max_orders:
            while total_cows_held < target_cows and money >= 500 and len(orders) < max_orders:
                orders.append(["BUY_ANIMAL", "COW", 1])
                money -= 400
                total_cows_held += 1

            while total_sheep_held < target_sheep and money >= 600 and len(orders) < max_orders:
                orders.append(["BUY_ANIMAL", "SHEEP", 1])
                money -= 500
                total_sheep_held += 1

        all_plot1_fully_stocked = (total_cows_held >= target_cows and total_sheep_held >= target_sheep)

        # -------------------------------------------------------------
        # 3. CONTROLLED LAND EXPANSION
        # -------------------------------------------------------------
        if day <= 20 and len(orders) < max_orders and all_plot1_fully_stocked:
            if "NE" not in self.state.unlocked_quadrants and money >= 2500 and day <= 8:
                orders.append(["BUY_LAND", "NE"])
                money -= 1000
                num_quads += 1
            elif "SW" not in self.state.unlocked_quadrants and money >= 5000 and day <= 15:
                orders.append(["BUY_LAND", "SW"])
                money -= 2000
                num_quads += 1

        # -------------------------------------------------------------
        # 4. ZONAL SEED PURCHASING
        # -------------------------------------------------------------
        if day <= 28 and len(orders) < max_orders:
            empty_tiles = self.state.get_empty_tiles()
            weed_tiles = self.state.get_weed_tiles()
            needed_counts = Counter()

            if day in (27, 28):
                total_empty = len(empty_tiles) + len(weed_tiles)
                needed_counts["WHEAT"] = max(needed_counts["WHEAT"], total_empty + 10)
            else:
                for pos in empty_tiles + weed_tiles:
                    c = get_target_crop_for_pos(pos, rem_days, day)
                    if c:
                        needed_counts[c] += 1

            wheat_buffer = max(0, 10 - self.state.seeds.get("WHEAT", 0))
            if wheat_buffer > 0:
                needed_counts["WHEAT"] += wheat_buffer

            spendable = max(0, money - 200) if day < 26 else money

            for crop in ["WHEAT", "MELON", "STRAWBERRY"]:
                if len(orders) >= max_orders:
                    break
                count = needed_counts.get(crop, 0)
                if count <= 0:
                    continue
                held = self.state.seeds.get(crop, 0)
                buy_needed = max(0, count - held)
                if buy_needed > 0:
                    seed_cost = CROPS[crop]["seed"]
                    affordable = min(buy_needed, int(spendable // seed_cost)) if seed_cost > 0 else 0
                    if affordable > 0:
                        batch = min(affordable, 25)
                        orders.append(["BUY_SEED", crop, batch])
                        spendable -= seed_cost * batch

        # -------------------------------------------------------------
        # 5. SHED INVENTORY LIQUIDATION
        # -------------------------------------------------------------
        for product in PRODUCTS:
            if len(orders) >= max_orders:
                break
            qty = self.state.shed.get(product, 0)
            if qty <= 0:
                continue

            if product == "WHEAT" and day < 29:
                if qty > 8:
                    orders.append(["SELL", "WHEAT", min(qty - 8, 20)])
                continue

            if product == "FERTILIZER" and day < 28:
                if qty > 4:
                    orders.append(["SELL", "FERTILIZER", qty - 4])
                continue

            if day >= 29 or rem_days <= 2:
                orders.append(["SELL", product, qty])
                continue
            cur_inv = self.state.market_inv.get(product, 10000)
            safe_qty = get_safe_sell_quantity(
                product=product,
                current_inv=cur_inv,
                available_in_shed=qty,
                unlocked_shops=self.state.unlocked_shops,
                remaining_days=rem_days,
            )

            if safe_qty > 0:
                orders.append(["SELL", product, safe_qty])

        return orders[:max_orders]
