"""Macro-Economic Planner: Dual-Plot Livestock Mega-Hub with Strict 12-Animal Procurement Gate."""

from collections import Counter
from src.constants import CROPS, PRODUCTS, LIVESTOCK_PLOTS, NW_WHEAT_TILES, NE_WHEAT_TILES
from src.state import FarmState
from src.market_model import get_safe_sell_quantity

FIBONACCI_COSTS = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377]


def get_hire_cost(n: int) -> int:
    if n < len(FIBONACCI_COSTS): return FIBONACCI_COSTS[n]
    a, b = FIBONACCI_COSTS[-2], FIBONACCI_COSTS[-1]
    for _ in range(n - len(FIBONACCI_COSTS) + 1):
        a, b = b, a + b
    return b


def get_target_crop_for_pos(pos: tuple[int, int], remaining_days: int, day: int) -> str | None:
    if day == 28: return "WHEAT"
    if day >= 29 or (day >= 26 and day != 28) or remaining_days <= 1: return None

    x, y = pos
    # Plot 1 (NW)
    if x < 5 and y < 5:
        if pos in NW_WHEAT_TILES: return "WHEAT"
        if day <= 10: return "MELON"
        elif day <= 25: return "STRAWBERRY"
        return "WHEAT"

    # Plot 2 (NE)
    if x >= 5 and y < 5:
        if pos in NE_WHEAT_TILES: return "WHEAT"
        if day <= 10: return "MELON"
        elif day <= 25: return "STRAWBERRY"
        return "WHEAT"

    # Plot 3 (SW): Targeted Melons & Wheat
    if x < 5 and y >= 5:
        if day <= 15 and remaining_days >= 10 and (x + y) % 3 == 0:
            return "MELON"
        return "WHEAT"

    # Plot 4 (SE): Wheat
    if x >= 5 and y >= 5:
        return "WHEAT"

    return "WHEAT"


class ZonalMacroPlanner:
    def __init__(self, state: FarmState):
        self.state = state

    def plan_market_orders(self) -> list:
        orders = []
        max_orders = 10
        money = self.state.money
        day = self.state.day
        rem_days = self.state.remaining_days
        num_quads = len(self.state.unlocked_quadrants)

        # 1. FIBONACCI DYNAMIC WORKFORCE HIRING
        base_hires = 5 if num_quads == 1 else (7 if num_quads == 2 else 9)
        harv_count = len(self.state.get_harvestable_tiles())

        if harv_count >= 15 and money >= 1000: base_hires = min(base_hires + 1, 10)
        if harv_count >= 25 and money >= 3000: base_hires = min(base_hires + 1, 11)
        if day <= 3: base_hires = min(base_hires, 5)
        elif money < 300: base_hires = min(base_hires, 5)

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

        # 2. LIVESTOCK PROCUREMENT (Plot 1: 4 Cows + 2 Sheep; Plot 2: 4 Cows + 2 Sheep)
        has_ne = ("NE" in self.state.unlocked_quadrants)
        target_cows = 8 if has_ne else 4
        target_sheep = 4 if has_ne else 2

        active_p1_cows = sum(1 for p, info in LIVESTOCK_PLOTS["NW"].items() if info[1] == "COW" and isinstance(self.state.get_tile(*p), dict) and self.state.get_tile(*p).get("animal") == "COW")
        active_p1_sheep = sum(1 for p, info in LIVESTOCK_PLOTS["NW"].items() if info[1] == "SHEEP" and isinstance(self.state.get_tile(*p), dict) and self.state.get_tile(*p).get("animal") == "SHEEP")

        active_p2_cows = sum(1 for p, info in LIVESTOCK_PLOTS["NE"].items() if info[1] == "COW" and isinstance(self.state.get_tile(*p), dict) and self.state.get_tile(*p).get("animal") == "COW")
        active_p2_sheep = sum(1 for p, info in LIVESTOCK_PLOTS["NE"].items() if info[1] == "SHEEP" and isinstance(self.state.get_tile(*p), dict) and self.state.get_tile(*p).get("animal") == "SHEEP")

        total_cows_held = active_p1_cows + active_p2_cows + self.state.shed.get("COW", 0) + sum(inv.get("COW", 0) for inv in self.state.inventories)
        total_sheep_held = active_p1_sheep + active_p2_sheep + self.state.shed.get("SHEEP", 0) + sum(inv.get("SHEEP", 0) for inv in self.state.inventories)

        if (day >= 1 or self.state.shed.get("WHEAT", 0) >= 2) and day <= 22 and len(orders) < max_orders:
            while total_cows_held < target_cows and money >= 400 and len(orders) < max_orders:
                orders.append(["BUY_ANIMAL", "COW", 1])
                money -= 400
                total_cows_held += 1

            while total_sheep_held < target_sheep and money >= 500 and len(orders) < max_orders:
                orders.append(["BUY_ANIMAL", "SHEEP", 1])
                money -= 500
                total_sheep_held += 1

        plot1_stocked = (total_cows_held >= 4 and total_sheep_held >= 2)
        all_12_animals_procured = (total_cows_held >= 8 and total_sheep_held >= 4)

        # 3. CONTROLLED LAND EXPANSION (Strict animal procurement before 3rd quadrant!)
        if day <= 20 and len(orders) < max_orders:
            if "NE" not in self.state.unlocked_quadrants and money >= 1800 and day <= 14 and plot1_stocked:
                orders.append(["BUY_LAND", "NE"])
                money -= 1000
                num_quads += 1
            elif "SW" not in self.state.unlocked_quadrants and "NE" in self.state.unlocked_quadrants and all_12_animals_procured and money >= 3500 and day <= 18:
                orders.append(["BUY_LAND", "SW"])
                money -= 2000
                num_quads += 1

        # 4. ZONAL SEED PURCHASING
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
                    if c: needed_counts[c] += 1

            wheat_buffer = max(0, 16 - self.state.seeds.get("WHEAT", 0))
            if wheat_buffer > 0: needed_counts["WHEAT"] += wheat_buffer

            spendable = max(0, money - 200) if day < 26 else money
            for crop in ["WHEAT", "MELON", "STRAWBERRY"]:
                if len(orders) >= max_orders: break
                count = needed_counts.get(crop, 0)
                if count <= 0: continue
                held = self.state.seeds.get(crop, 0)
                buy_needed = max(0, count - held)
                if buy_needed > 0:
                    seed_cost = CROPS[crop]["seed"]
                    affordable = min(buy_needed, int(spendable // seed_cost)) if seed_cost > 0 else 0
                    if affordable > 0:
                        batch = min(affordable, 25)
                        orders.append(["BUY_SEED", crop, batch])
                        spendable -= seed_cost * batch

        # 5. SHED INVENTORY LIQUIDATION (Reserve 14 Wheat for feed & 4 Fertilizer)
        for product in PRODUCTS:
            if len(orders) >= max_orders: break
            qty = self.state.shed.get(product, 0)
            if qty <= 0: continue

            if product == "WHEAT" and day < 29:
                if qty > 14: orders.append(["SELL", "WHEAT", min(qty - 14, 20)])
                continue
            if product == "FERTILIZER" and day < 28:
                if qty > 4: orders.append(["SELL", "FERTILIZER", qty - 4])
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
