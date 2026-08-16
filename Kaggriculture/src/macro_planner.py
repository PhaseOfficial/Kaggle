"""Macro-Economic Planner: 6 livestock plots exclusively in Plot 1 (NW), 100% crops on expansions."""

from collections import Counter
from src.constants import CROPS, PRODUCTS, LIVESTOCK_PLOTS
from src.state import FarmState
from src.market_model import get_safe_sell_quantity


def get_target_crop_for_pos(pos: tuple[int, int], remaining_days: int, day: int) -> str | None:
    if remaining_days <= 3 or day >= 26:
        return None

    dist = abs(pos[0] - 4) + abs(pos[1] - 4)
    # Core Zone (d <= 1): Wheat & Carrot for rapid food and cash turnover
    if dist <= 1:
        if (pos[0] + pos[1]) % 2 == 0:
            return "CARROT"
        return "WHEAT"
    # Mid Zone (2 <= d <= 3): Tomato on Days 0-21 -> Wheat on Days 22-26
    if dist <= 3:
        if day <= 21 and remaining_days >= 8:
            return "TOMATO"
        return "WHEAT"
    # Outer Zone (d >= 4): Melons on Days 0-19 -> Wheat on Days 20-26
    if day <= 19 and remaining_days >= 10:
        return "MELON"
    return "WHEAT"


class ZonalMacroPlanner:
    """Manages full-farm budget, guaranteed daily hiring, livestock procurement, and liquidation."""

    def __init__(self, state: FarmState):
        self.state = state

    def plan_market_orders(self) -> list:
        orders = []
        max_orders = 10
        money = self.state.money
        day = self.state.day
        hour = self.state.hour
        rem_days = self.state.remaining_days
        num_quads = len(self.state.unlocked_quadrants)

        # 1. GUARANTEED DAILY FARMHAND HIRING AT HOUR 0
        if hour == 0 and day <= 27 and money >= 12:
            target_hires = 5 if num_quads == 1 else (8 if num_quads == 2 else (10 if num_quads == 3 else 12))
            needed_hires = max(0, target_hires - self.state.hires_today)
            for _ in range(needed_hires):
                if len(orders) >= max_orders:
                    break
                orders.append(["HIRE"])

        # 2. Livestock Purchasing (Target for the First Plot NW: 1 Goose, 3 Cows, 2 Sheep = 6 total)
        target_geese = 1
        target_cows = 3
        target_sheep = 2

        total_geese_held = sum(1 for p, info in LIVESTOCK_PLOTS["NW"].items() if info[1] == "GOOSE" and isinstance(self.state.get_tile(*p), dict) and self.state.get_tile(*p).get("animal") == "GOOSE") + self.state.shed.get("GOOSE", 0) + sum(inv.get("GOOSE", 0) for inv in self.state.inventories)
        total_cows_held = sum(1 for p, info in LIVESTOCK_PLOTS["NW"].items() if info[1] == "COW" and isinstance(self.state.get_tile(*p), dict) and self.state.get_tile(*p).get("animal") == "COW") + self.state.shed.get("COW", 0) + sum(inv.get("COW", 0) for inv in self.state.inventories)
        total_sheep_held = sum(1 for p, info in LIVESTOCK_PLOTS["NW"].items() if info[1] == "SHEEP" and isinstance(self.state.get_tile(*p), dict) and self.state.get_tile(*p).get("animal") == "SHEEP") + self.state.shed.get("SHEEP", 0) + sum(inv.get("SHEEP", 0) for inv in self.state.inventories)

        # Procure animals on Day 2+ once wheat feed is available
        if (day >= 2 or self.state.shed.get("WHEAT", 0) >= 5) and day <= 20 and len(orders) < max_orders:
            for anim, held, target, cost in [("GOOSE", total_geese_held, target_geese, 300), ("COW", total_cows_held, target_cows, 400), ("SHEEP", total_sheep_held, target_sheep, 500)]:
                if len(orders) >= max_orders:
                    break
                if held < target and money >= cost + 100:
                    orders.append(["BUY_ANIMAL", anim, 1])
                    money -= cost
                    if anim == "GOOSE": total_geese_held += 1
                    elif anim == "COW": total_cows_held += 1
                    elif anim == "SHEEP": total_sheep_held += 1

        all_plot1_fully_stocked = (total_geese_held >= target_geese and total_cows_held >= target_cows and total_sheep_held >= target_sheep)

        # 3. Cyclic Land Expansion (ONLY IF PLOT 1 HAS ALL 6 LIVESTOCK SLOTS FILLED)
        if day <= 23 and len(orders) < max_orders and all_plot1_fully_stocked:
            if "NE" not in self.state.unlocked_quadrants and money >= 4000 and day <= 16:
                orders.append(["BUY_LAND", "NE"])
                money -= 1000
                num_quads += 1
            elif "SW" not in self.state.unlocked_quadrants and money >= 6000 and day <= 20:
                orders.append(["BUY_LAND", "SW"])
                money -= 2000
                num_quads += 1
            elif "SE" not in self.state.unlocked_quadrants and money >= 12000 and day <= 23:
                orders.append(["BUY_LAND", "SE"])
                money -= 4000
                num_quads += 1

        # 4. Zonal Seed Purchasing & Rolling Buffer (Maintain 10 Wheat seeds)
        if day <= 25 and len(orders) < max_orders:
            empty_tiles = self.state.get_empty_tiles()
            needed_counts = Counter()
            for pos in empty_tiles:
                c = get_target_crop_for_pos(pos, rem_days, day)
                if c:
                    needed_counts[c] += 1
            wheat_buffer = max(0, 10 - self.state.seeds.get("WHEAT", 0))
            if wheat_buffer > 0:
                needed_counts["WHEAT"] += wheat_buffer

            spendable = max(0, money - 250) if day < 26 else money

            for crop, count in needed_counts.items():
                if len(orders) >= max_orders:
                    break
                held = self.state.seeds.get(crop, 0)
                buy_needed = max(0, count - held)
                if buy_needed > 0:
                    seed_cost = CROPS[crop]["seed"]
                    affordable = min(buy_needed, int(spendable // seed_cost)) if seed_cost > 0 else 0
                    if affordable > 0:
                        batch = min(affordable, 8)
                        orders.append(["BUY_SEED", crop, batch])
                        spendable -= seed_cost * batch

        # 5. Shed Inventory Liquidation (Reserve 15 Wheat for animal feed)
        for product in PRODUCTS:
            if len(orders) >= max_orders:
                break
            qty = self.state.shed.get(product, 0)
            if qty <= 0:
                continue

            if product == "WHEAT" and day < 28:
                if qty > 15:
                    orders.append(["SELL", "WHEAT", min(qty - 15, 20)])
                continue

            if day >= 27 or rem_days <= 3:
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
