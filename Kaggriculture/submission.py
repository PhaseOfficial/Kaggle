"""
Master Industrial & Livestock Farm Agent for Kaggriculture.
Features:
- 6 Dedicated Livestock Plots exclusively in the First Plot (NW): 1 Goose in Coop, 3 Cattle in Pastures, 2 Sheep in Pastures
- 100% Crop Mega-Farms on Expansion Plots (NE, SW, SE): Full surface area dedicated to high-yield Melons ($1,500/tile), Tomatoes ($240/day), and Wheat compounding
- Strict Pre-Expansion Livestock Gate: The 6 livestock slots in Plot 1 MUST be fully stocked BEFORE expanding land (NE -> SW -> SE)
- Guaranteed Daily Feeding with 15-Wheat reserve buffer (prevents starvation)
- Daily care & harvests (Eggs, Milk, Wool, and $100 Fertilizers)
- 5-Farmhand workforce scaling (up to 13 workers / 312 actions/day)
- BFS boundary-locked navigation strictly within unlocked farm borders
- Zero-waste Day 27-30 terminal sweep and 100% shed cash liquidation
"""

import math
from collections import Counter, deque

CROPS = {
    "WHEAT": {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT": {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO": {"seed": 50, "first_yield_day": 8, "max_yield_day": 11, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 16, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON": {"seed": 80, "first_yield_day": 10, "max_yield_day": 10, "interval": 0, "max_yield": 6, "ongoing": False},
}

# 6 Dedicated Livestock Plots ONLY in the First Plot (NW). Expansion plots (NE, SW, SE) are 100% crops!
LIVESTOCK_TILES = {
    "NW": {
        (4, 3): ("COOP", "GOOSE"),
        (3, 4): ("PASTURE", "COW"),
        (3, 3): ("PASTURE", "SHEEP"),
        (4, 2): ("PASTURE", "COW"),
        (2, 4): ("PASTURE", "COW"),
        (3, 2): ("PASTURE", "SHEEP"),
    },
    "NE": {},
    "SW": {},
    "SE": {},
}

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


def get_price(product: str, inv: int) -> int:
    params = MARKET_PARAMS.get(product)
    if not params: return 1
    base = params["base"]
    I0 = params.get("I0", MARKET_I0)
    T = params["T"]
    if inv == I0: return base
    if inv < I0:
        f_T = shape_func(params["below_func"], T, T)
        amp = (params["below_target"] * base) / f_T if f_T > 0 else 0.0
        return max(PRICE_FLOOR, round(base + amp * shape_func(params["below_func"], I0 - inv, T)))
    else:
        f_T = shape_func(params["above_func"], T, T)
        amp = (params["above_target"] * base) / f_T if f_T > 0 else 0.0
        return max(PRICE_FLOOR, round(base - amp * shape_func(params["above_func"], inv - I0, T)))


def get_safe_sell_quantity(product: str, current_inv: int, available_in_shed: int, remaining_days: int) -> int:
    if available_in_shed <= 0: return 0
    if remaining_days <= 3: return available_in_shed
    if product in ("WHEAT", "EGG"): return min(available_in_shed, 20)
    safe_q = 0
    test_inv = current_inv
    min_price = max(PRICE_FLOOR, int(MARKET_PARAMS.get(product, {}).get("base", 1) * 0.5))
    for _ in range(min(available_in_shed, 15)):
        if get_price(product, test_inv) < min_price: break
        safe_q += 1
        test_inv += 1
    return max(1, safe_q) if safe_q > 0 else (1 if available_in_shed > 50 else 0)


class FarmState:
    def __init__(self, obs: dict):
        self.raw_obs = obs
        self.player_id = obs.get("player", 0)
        self.day = obs.get("day", 0)
        self.hour = obs.get("hour", 0)
        self.step = obs.get("step", self.day * 24 + self.hour)
        self.remaining_days = max(0, 30 - self.day)

        farms = obs.get("farms", [])
        self.my_farm = farms[self.player_id] if self.player_id < len(farms) else {}
        self.money = float(self.my_farm.get("money", 0))
        self.farmer_pos = tuple(self.my_farm.get("farmer", [4, 4]))
        self.hands_pos = [tuple(h) for h in self.my_farm.get("hands", [])]
        self.tiles = self.my_farm.get("tiles", [])
        self.unlocked_quadrants = set(self.my_farm.get("unlocked_quadrants", ["NW"]))
        self.hires_today = self.my_farm.get("hires_today", 0)

        private = obs.get("private", {}) or {}
        self.shed = private.get("shed", {}) or {}
        self.seeds = private.get("seeds", {}) or {}
        self.inventories = private.get("inventories", [{}])

        market = obs.get("market", {}) or {}
        self.market_inv = market.get("inventory", {}) or {}
        self.board_size = len(self.tiles) if self.tiles else 10

    def is_tile_unlocked(self, x: int, y: int) -> bool:
        if x < 0 or x >= self.board_size or y < 0 or y >= self.board_size:
            return False
        quad_x = "W" if x < self.board_size // 2 else "E"
        quad_y = "N" if y < self.board_size // 2 else "S"
        return (quad_y + quad_x) in self.unlocked_quadrants

    def get_tile(self, x: int, y: int):
        if 0 <= y < len(self.tiles) and 0 <= x < len(self.tiles[y]):
            return self.tiles[y][x]
        return "LOCKED"

    def get_all_unlocked_coords(self) -> list[tuple[int, int]]:
        coords = []
        for y in range(self.board_size):
            for x in range(self.board_size):
                if self.is_tile_unlocked(x, y):
                    coords.append((x, y))
        return coords

    def get_empty_tiles(self) -> list[tuple[int, int]]:
        livestock_plots = set(LIVESTOCK_TILES.get("NW", {}).keys())
        return [(x, y) for (x, y) in self.get_all_unlocked_coords() if self.get_tile(x, y) is None and (x, y) not in livestock_plots]

    def get_weed_tiles(self) -> list[tuple[int, int]]:
        weeds = []
        for x, y in self.get_all_unlocked_coords():
            t = self.get_tile(x, y)
            if isinstance(t, dict) and t.get("kind") == "WEED":
                weeds.append((x, y))
        return weeds

    def get_urgent_water_tiles(self) -> list[tuple[int, int]]:
        urgent = []
        for x, y in self.get_all_unlocked_coords():
            t = self.get_tile(x, y)
            if isinstance(t, dict) and t.get("kind") == "PLANT":
                if not t.get("watered_today", False) and t.get("consecutive_unwatered", 0) >= 1:
                    urgent.append((x, y))
        return urgent

    def get_routine_water_tiles(self) -> list[tuple[int, int]]:
        water_needed = []
        for x, y in self.get_all_unlocked_coords():
            t = self.get_tile(x, y)
            if isinstance(t, dict) and t.get("kind") == "PLANT":
                if not t.get("watered_today", False):
                    water_needed.append((x, y))
        return water_needed

    def get_harvestable_tiles(self) -> list[tuple[int, int]]:
        ready = []
        for x, y in self.get_all_unlocked_coords():
            t = self.get_tile(x, y)
            if isinstance(t, dict):
                if t.get("kind") == "PLANT":
                    crop = t.get("crop")
                    crop_info = CROPS.get(crop, {})
                    age = self.day - t.get("planted_day", 0)
                    ongoing = crop_info.get("ongoing", False)
                    max_yield_day = crop_info.get("max_yield_day", 4)
                    yield_units = t.get("yield_units", 0)
                    if yield_units > 0:
                        if self.day >= 27 or ongoing or age >= max_yield_day or self.remaining_days <= 1:
                            ready.append((x, y))
                elif t.get("kind") in ("COOP", "PASTURE"):
                    if t.get("yield_units", 0) > 0:
                        ready.append((x, y))
        return ready


def get_bfs_step(start: tuple[int, int], target: tuple[int, int], unlocked_tiles: set[tuple[int, int]]) -> str:
    if start == target or target not in unlocked_tiles:
        return "PASS"
    queue = deque([[start]])
    visited = {start}
    while queue:
        path = queue.popleft()
        curr = path[-1]
        if curr == target:
            if len(path) > 1:
                first_step = path[1]
                dx = first_step[0] - start[0]
                dy = first_step[1] - start[1]
                if dx == 1: return "EAST"
                if dx == -1: return "WEST"
                if dy == 1: return "SOUTH"
                if dy == -1: return "NORTH"
            return "PASS"
        for dx, dy in [(0, -1), (0, 1), (1, 0), (-1, 0)]:
            nxt = (curr[0] + dx, curr[1] + dy)
            if nxt in unlocked_tiles and nxt not in visited:
                visited.add(nxt)
                queue.append(path + [nxt])
    return "PASS"


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


class MasterIndustrialAgent:
    def plan_market(self, state: FarmState) -> list:
        orders = []
        max_orders = 10
        money = state.money
        day = state.day
        hour = state.hour
        rem_days = state.remaining_days
        num_quads = len(state.unlocked_quadrants)

        # 1. GUARANTEED DAILY FARMHAND HIRING AT HOUR 0
        if hour == 0 and day <= 27 and money >= 12:
            target_hires = 5 if num_quads == 1 else (8 if num_quads == 2 else (10 if num_quads == 3 else 12))
            needed_hires = max(0, target_hires - state.hires_today)
            for _ in range(needed_hires):
                if len(orders) >= max_orders:
                    break
                orders.append(["HIRE"])

        # 2. Livestock Purchasing (Target for the First Plot NW: 1 Goose, 3 Cows, 2 Sheep = 6 total)
        target_geese = 1
        target_cows = 3
        target_sheep = 2

        total_geese_held = sum(1 for p, info in LIVESTOCK_TILES["NW"].items() if info[1] == "GOOSE" and isinstance(state.get_tile(*p), dict) and state.get_tile(*p).get("animal") == "GOOSE") + state.shed.get("GOOSE", 0) + sum(inv.get("GOOSE", 0) for inv in state.inventories)
        total_cows_held = sum(1 for p, info in LIVESTOCK_TILES["NW"].items() if info[1] == "COW" and isinstance(state.get_tile(*p), dict) and state.get_tile(*p).get("animal") == "COW") + state.shed.get("COW", 0) + sum(inv.get("COW", 0) for inv in state.inventories)
        total_sheep_held = sum(1 for p, info in LIVESTOCK_TILES["NW"].items() if info[1] == "SHEEP" and isinstance(state.get_tile(*p), dict) and state.get_tile(*p).get("animal") == "SHEEP") + state.shed.get("SHEEP", 0) + sum(inv.get("SHEEP", 0) for inv in state.inventories)

        # Procure animals on Day 2+ once wheat feed is available
        if (day >= 2 or state.shed.get("WHEAT", 0) >= 5) and day <= 20 and len(orders) < max_orders:
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
            if "NE" not in state.unlocked_quadrants and money >= 4000 and day <= 16:
                orders.append(["BUY_LAND", "NE"])
                money -= 1000
                num_quads += 1
            elif "SW" not in state.unlocked_quadrants and money >= 6000 and day <= 20:
                orders.append(["BUY_LAND", "SW"])
                money -= 2000
                num_quads += 1
            elif "SE" not in state.unlocked_quadrants and money >= 12000 and day <= 23:
                orders.append(["BUY_LAND", "SE"])
                money -= 4000
                num_quads += 1

        # 4. Zonal Seed Purchasing & Rolling Buffer (Maintain 10 Wheat seeds)
        if day <= 25 and len(orders) < max_orders:
            empty_tiles = state.get_empty_tiles()
            needed_counts = Counter()
            for pos in empty_tiles:
                c = get_target_crop_for_pos(pos, rem_days, day)
                if c:
                    needed_counts[c] += 1
            wheat_buffer = max(0, 10 - state.seeds.get("WHEAT", 0))
            if wheat_buffer > 0:
                needed_counts["WHEAT"] += wheat_buffer

            spendable = max(0, money - 250) if day < 26 else money

            for crop, count in needed_counts.items():
                if len(orders) >= max_orders:
                    break
                held = state.seeds.get(crop, 0)
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
            qty = state.shed.get(product, 0)
            if qty <= 0:
                continue

            if product == "WHEAT" and day < 28:
                if qty > 15:
                    orders.append(["SELL", "WHEAT", min(qty - 15, 20)])
                continue

            if day >= 27 or rem_days <= 3:
                orders.append(["SELL", product, qty])
                continue
            cur_inv = state.market_inv.get(product, 10000)
            safe_q = get_safe_sell_quantity(product, cur_inv, qty, rem_days)
            if safe_q > 0:
                orders.append(["SELL", product, safe_q])

        return orders[:max_orders]

    def plan_workers(self, state: FarmState) -> tuple[list, list]:
        workers = [state.farmer_pos] + state.hands_pos
        day = state.day
        rem_days = state.remaining_days
        unlocked_set = set(state.get_all_unlocked_coords())

        # Active livestock exclusively in NW
        active_livestock = dict(LIVESTOCK_TILES["NW"])

        urgent_water = set(state.get_urgent_water_tiles())
        routine_water = set(state.get_routine_water_tiles())
        harvestable = set(state.get_harvestable_tiles())
        weeds = set(state.get_weed_tiles())
        empty = set(state.get_empty_tiles())

        assigned_targets = set()
        worker_actions = []
        available_seeds = dict(state.seeds)

        for w_idx, w_pos in enumerate(workers):
            tile = state.get_tile(*w_pos)
            action = None

            # --- A. Farmer Special: Pickup Animal from Shed if needed ---
            if w_idx == 0:
                inv_0 = state.inventories[0] if state.inventories else {}
                has_animal_in_inv = any(inv_0.get(a, 0) > 0 for a in ["GOOSE", "COW", "SHEEP"])
                has_animal_in_shed = any(state.shed.get(a, 0) > 0 for a in ["GOOSE", "COW", "SHEEP"])

                if not has_animal_in_inv and has_animal_in_shed:
                    if w_pos == (4, 4):
                        for anim in ["GOOSE", "COW", "SHEEP"]:
                            if state.shed.get(anim, 0) > 0:
                                action = ["PICKUP", anim, 1]
                                break
                    else:
                        step = get_bfs_step(w_pos, (4, 4), unlocked_set)
                        action = [step] if step != "PASS" else ["PASS"]

                elif has_animal_in_inv:
                    for pos, (struct, anim) in active_livestock.items():
                        if inv_0.get(anim, 0) > 0:
                            t_target = state.get_tile(*pos)
                            if t_target is None or (isinstance(t_target, dict) and t_target.get("animal") is None):
                                if w_pos != pos:
                                    step = get_bfs_step(w_pos, pos, unlocked_set)
                                    action = [step] if step != "PASS" else ["PASS"]
                                else:
                                    if tile is None:
                                        action = ["BUILD_COOP"] if struct == "COOP" else ["BUILD_PASTURE"]
                                    elif isinstance(tile, dict) and tile.get("animal") is None:
                                        action = ["PLACE", anim]
                                break

            # --- B. Livestock Care on Standing Plot ---
            if action is None and w_pos in active_livestock and w_pos not in assigned_targets:
                req_struct, req_animal = active_livestock[w_pos]
                if isinstance(tile, dict) and tile.get("animal"):
                    if not tile.get("fed_today", False) and (state.shed.get("WHEAT", 0) > 0 or (w_idx < len(state.inventories) and state.inventories[w_idx].get("WHEAT", 0) > 0)):
                        action = ["FEED"]
                        assigned_targets.add(w_pos)
                    elif tile.get("yield_units", 0) > 0:
                        action = ["HARVEST"]
                        assigned_targets.add(w_pos)
                    elif tile.get("fertilizer_available", False):
                        action = ["COLLECT_FERTILIZER"]
                        assigned_targets.add(w_pos)
                    elif not tile.get("cared_today", False):
                        action = ["CARE"]
                        assigned_targets.add(w_pos)

            # --- C. Crop Standing Actions ---
            if action is None:
                if w_pos in harvestable and w_pos not in assigned_targets:
                    action = ["HARVEST"]
                    assigned_targets.add(w_pos)
                elif (w_pos in urgent_water or w_pos in routine_water) and w_pos not in assigned_targets:
                    action = ["WATER"]
                    assigned_targets.add(w_pos)
                elif w_pos in empty and day <= 25 and w_pos not in assigned_targets:
                    pref_crop = get_target_crop_for_pos(w_pos, rem_days, day)
                    chosen_crop = None
                    if pref_crop and available_seeds.get(pref_crop, 0) > 0:
                        chosen_crop = pref_crop
                    elif available_seeds.get("WHEAT", 0) > 0:
                        chosen_crop = "WHEAT"
                    elif available_seeds.get("CARROT", 0) > 0:
                        chosen_crop = "CARROT"
                    else:
                        for s_name, s_count in available_seeds.items():
                            if s_count > 0:
                                chosen_crop = s_name
                                break
                    if chosen_crop:
                        action = ["PLANT", chosen_crop]
                        available_seeds[chosen_crop] -= 1
                        assigned_targets.add(w_pos)
                elif w_pos in weeds and w_pos not in assigned_targets:
                    action = ["DIG"]
                    assigned_targets.add(w_pos)

            # --- D. BFS Navigation to Next Priority Task ---
            if action is None:
                best_target = None

                # On Days 27-30, HARVEST IS PRIORITY 0!
                if day >= 27:
                    p_harv = [p for p in harvestable if p not in assigned_targets]
                    if p_harv:
                        best_target = min(p_harv, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 0: Livestock needs (Feed, Harvest, Collect Fertilizer)
                if not best_target:
                    for l_pos in active_livestock:
                        if l_pos not in assigned_targets:
                            t = state.get_tile(*l_pos)
                            if isinstance(t, dict) and t.get("animal"):
                                if (not t.get("fed_today", False) and state.shed.get("WHEAT", 0) > 0) or t.get("yield_units", 0) > 0 or t.get("fertilizer_available", False):
                                    best_target = l_pos
                                    break

                # Priority 1: Urgent water
                if not best_target:
                    p0 = [p for p in urgent_water if p not in assigned_targets]
                    if p0:
                        best_target = min(p0, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 2: Ready harvests
                if not best_target:
                    p1 = [p for p in harvestable if p not in assigned_targets]
                    if p1:
                        best_target = min(p1, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 3: Routine daily water
                if not best_target:
                    p2 = [p for p in routine_water if p not in assigned_targets]
                    if p2:
                        best_target = min(p2, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 4: Empty tiles to plant
                if not best_target and day <= 25 and sum(available_seeds.values()) > 0:
                    p3 = [p for p in empty if p not in assigned_targets]
                    if p3:
                        best_target = min(p3, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 5: Weeds to clear
                if not best_target:
                    p4 = [p for p in weeds if p not in assigned_targets]
                    if p4:
                        best_target = min(p4, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if best_target and best_target != w_pos:
                    assigned_targets.add(best_target)
                    step = get_bfs_step(w_pos, best_target, unlocked_set)
                    action = [step] if step != "PASS" else ["PASS"]
                else:
                    action = ["PASS"]

            worker_actions.append(action)

        farmer_act = worker_actions[0] if worker_actions else ["PASS"]
        hands_act = worker_actions[1:] if len(worker_actions) > 1 else []
        return farmer_act, hands_act


_master_agent = MasterIndustrialAgent()


def agent(obs: dict) -> dict:
    """Kaggriculture agent decision function."""
    try:
        state = FarmState(obs)
        market = _master_agent.plan_market(state)
        farmer, hands = _master_agent.plan_workers(state)
        return {"farmer": farmer, "hands": hands, "market": market}
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}
