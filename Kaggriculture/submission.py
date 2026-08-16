"""
Master Industrial & Livestock Farm Agent for Kaggriculture.
Features:
- Plot 1 (NW) Livestock: 2 Cows and 2 Sheep (Pastures)
- Plot 1 (NW) Crop Engine: 7 dedicated Wheat tiles + Melons on initial phase -> after first Melon harvest (Day 10+), shifts to Strawberries & Tomatoes!
- Plot 2 (NE) Crop Engine: High-Yield Watermelon Production (80% Melons on Days 0-19)
- Plot 3 (SW) & Plot 4 (SE) Blitz: 100% Whole-Plot 25-Tile Seeding (Wheat 60% & Carrot 40%)
- Continuous Workforce Hiring (replenishes hands up to 12 hands / 13 workers / 312 actions/day)
- Priority Weed Clearing & Batch-25 Seed Buying
- Pre-Expansion Gate: 2 Cows & 2 Sheep stocked before land expansion
- Strict Zero-Loss Cash Reserves ($6k+ for SW, $12k+ for SE)
- Scaled Workforce & BFS boundary-locked navigation
- Flawless Zero-Waste Days 27-30 terminal harvest sweep and 100% shed cash liquidation
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

# 4 Livestock Plots in First Plot (NW): 2 Cows and 2 Sheep. Expansion plots (NE, SW, SE) are 100% crops!
LIVESTOCK_TILES = {
    "NW": {
        (3, 4): ("PASTURE", "COW"),
        (4, 2): ("PASTURE", "COW"),
        (3, 3): ("PASTURE", "SHEEP"),
        (3, 2): ("PASTURE", "SHEEP"),
    },
    "NE": {},
    "SW": {},
    "SE": {},
}

# 7 Dedicated Wheat Coordinates in Plot 1 (NW)
NW_WHEAT_TILES = {(4, 3), (2, 4), (1, 4), (0, 4), (4, 1), (4, 0), (2, 3)}

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
        quad_x = "W" if x < 5 else "E"
        quad_y = "N" if y < 5 else "S"
        return (quad_y + quad_x) in self.unlocked_quadrants

    def get_quadrant_for_pos(self, x: int, y: int) -> str:
        quad_x = "W" if x < 5 else "E"
        quad_y = "N" if y < 5 else "S"
        return quad_y + quad_x

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
                        if self.day >= 26 or ongoing or age >= max_yield_day or self.remaining_days <= 1:
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

    # Plot 1 (NW): x < 5 and y < 5
    if pos[0] < 5 and pos[1] < 5:
        # 1. 7 Dedicated Wheat coordinates
        if pos in NW_WHEAT_TILES:
            return "WHEAT"
        # 2. Remaining 14 tiles: Initial Melons -> after first Melon harvest (Day 10+), shift to Strawberries & Tomatoes!
        if day <= 10:
            return "MELON"
        elif day <= 21:
            if (pos[0] + pos[1]) % 2 == 0:
                return "STRAWBERRY"
            return "TOMATO"
        return "WHEAT"

    # Plot 2 (NE): Covers x in [5, 9], y in [0, 4] -> HIGH-YIELD WATERMELON PRODUCTION (Days 0-19)
    if pos[0] >= 5 and pos[1] < 5:
        if day <= 19 and remaining_days >= 10:
            if (pos[0] + pos[1]) % 4 != 0:
                return "MELON"
            return "WHEAT"
        elif day <= 21 and remaining_days >= 8:
            return "TOMATO"
        return "WHEAT"

    # Plot 3 (SW): Covers x in [0, 4], y in [5, 9] -> 100% 2-day rapid turnover mix (Wheat 60% & Carrot 40%)
    if pos[0] < 5 and pos[1] >= 5:
        if (pos[0] + pos[1]) % 2 == 1:
            return "WHEAT"
        return "CARROT"

    # Plot 4 (SE): Covers x in [5, 9], y in [5, 9] -> 100% 2-day rapid turnover mix (Wheat 60% & Carrot 40%)
    if pos[0] >= 5 and pos[1] >= 5:
        if (pos[0] + pos[1]) % 2 == 1:
            return "WHEAT"
        return "CARROT"

    return "WHEAT"


class MasterIndustrialAgent:
    def plan_market(self, state: FarmState) -> list:
        orders = []
        max_orders = 10
        money = state.money
        day = state.day
        rem_days = state.remaining_days
        num_quads = len(state.unlocked_quadrants)

        # 1. CONTINUOUS WORKFORCE HIRING
        target_hires = 5 if num_quads == 1 else (8 if num_quads == 2 else (10 if num_quads == 3 else 12))
        needed_hires = max(0, target_hires - state.hires_today)
        if day <= 28 and money >= 12 and needed_hires > 0:
            for _ in range(needed_hires):
                if len(orders) >= max_orders:
                    break
                orders.append(["HIRE"])

        # 2. Livestock Purchasing Queue (2 Cows -> 2 Sheep in NW)
        target_cows = 2
        target_sheep = 2

        total_cows_held = sum(1 for p, info in LIVESTOCK_TILES["NW"].items() if info[1] == "COW" and isinstance(state.get_tile(*p), dict) and state.get_tile(*p).get("animal") == "COW") + state.shed.get("COW", 0) + sum(inv.get("COW", 0) for inv in state.inventories)
        total_sheep_held = sum(1 for p, info in LIVESTOCK_TILES["NW"].items() if info[1] == "SHEEP" and isinstance(state.get_tile(*p), dict) and state.get_tile(*p).get("animal") == "SHEEP") + state.shed.get("SHEEP", 0) + sum(inv.get("SHEEP", 0) for inv in state.inventories)

        # Procure animals on Day 2+ once wheat feed is available
        if (day >= 2 or state.shed.get("WHEAT", 0) >= 5) and day <= 20 and len(orders) < max_orders:
            # 2 Cows ($400 each)
            while total_cows_held < target_cows and money >= 500 and len(orders) < max_orders:
                orders.append(["BUY_ANIMAL", "COW", 1])
                money -= 400
                total_cows_held += 1

            # 2 Sheep ($500 each)
            while total_sheep_held < target_sheep and money >= 600 and len(orders) < max_orders:
                orders.append(["BUY_ANIMAL", "SHEEP", 1])
                money -= 500
                total_sheep_held += 1

        all_plot1_fully_stocked = (total_cows_held >= target_cows and total_sheep_held >= target_sheep)

        # 3. Cyclic Land Expansion with Zero-Loss Protection (ONLY IF PLOT 1 HAS ALL 4 LIVESTOCK SLOTS FILLED)
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

        # 4. Zonal Seed Purchasing & Rolling Buffer
        if day <= 25 and len(orders) < max_orders:
            empty_tiles = state.get_empty_tiles()
            weed_tiles = state.get_weed_tiles()
            needed_counts = Counter()
            for pos in empty_tiles + weed_tiles:
                c = get_target_crop_for_pos(pos, rem_days, day)
                if c:
                    needed_counts[c] += 1
            wheat_buffer = max(0, 15 - state.seeds.get("WHEAT", 0))
            if wheat_buffer > 0:
                needed_counts["WHEAT"] += wheat_buffer

            spendable = max(0, money - 200) if day < 26 else money

            ordered_crops = ["MELON", "STRAWBERRY", "TOMATO", "WHEAT", "CARROT"]
            for crop in ordered_crops:
                if len(orders) >= max_orders:
                    break
                count = needed_counts.get(crop, 0)
                if count <= 0:
                    continue
                held = state.seeds.get(crop, 0)
                buy_needed = max(0, count - held)
                if buy_needed > 0:
                    seed_cost = CROPS[crop]["seed"]
                    affordable = min(buy_needed, int(spendable // seed_cost)) if seed_cost > 0 else 0
                    if affordable > 0:
                        batch = min(affordable, 25)
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

        active_quads_list = sorted(list(state.unlocked_quadrants))
        worker_quad_map = {}
        for w_idx in range(len(workers)):
            if w_idx == 0:
                worker_quad_map[w_idx] = "NW"
            else:
                worker_quad_map[w_idx] = active_quads_list[(w_idx - 1) % len(active_quads_list)]

        assigned_targets = set()
        fed_animals_today = set()
        worker_actions = []
        available_seeds = dict(state.seeds)

        for w_idx, w_pos in enumerate(workers):
            tile = state.get_tile(*w_pos)
            action = None
            assigned_quad = worker_quad_map.get(w_idx, "NW")

            # --- A. Farmer Special: Pickup Animal from Shed if needed ---
            if w_idx == 0 and day <= 24:
                inv_0 = state.inventories[0] if state.inventories else {}
                has_animal_in_inv = any(inv_0.get(a, 0) > 0 for a in ["COW", "SHEEP"])
                has_animal_in_shed = any(state.shed.get(a, 0) > 0 for a in ["COW", "SHEEP"])

                if not has_animal_in_inv and has_animal_in_shed:
                    if w_pos == (4, 4):
                        for anim in ["COW", "SHEEP"]:
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
                                        action = ["BUILD_PASTURE"]
                                    elif isinstance(tile, dict) and tile.get("animal") is None:
                                        action = ["PLACE", anim]
                                break

            # --- B. Livestock Care on Standing Plot (Once per day per animal) ---
            if action is None and w_pos in active_livestock and w_pos not in assigned_targets:
                req_struct, req_animal = active_livestock[w_pos]
                if isinstance(tile, dict) and tile.get("animal"):
                    if not tile.get("fed_today", False) and w_pos not in fed_animals_today and (state.shed.get("WHEAT", 0) > 0 or (w_idx < len(state.inventories) and state.inventories[w_idx].get("WHEAT", 0) > 0)):
                        action = ["FEED"]
                        fed_animals_today.add(w_pos)
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
                elif day < 27 and (w_pos in urgent_water or w_pos in routine_water) and w_pos not in assigned_targets:
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

            # --- D. BFS Navigation ---
            if action is None:
                best_target = None

                # On Days 26-30, HARVEST IS ABSOLUTE TOP PRIORITY FOR ALL WORKERS!
                if day >= 26:
                    p_harv_local = [p for p in harvestable if p not in assigned_targets and state.get_quadrant_for_pos(*p) == assigned_quad]
                    p_harv_any = [p for p in harvestable if p not in assigned_targets]
                    p_harv = p_harv_local if p_harv_local else p_harv_any
                    if p_harv:
                        best_target = min(p_harv, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 0: Livestock needs
                if not best_target and w_idx == 0:
                    for l_pos in active_livestock:
                        if l_pos not in assigned_targets and l_pos not in fed_animals_today:
                            t = state.get_tile(*l_pos)
                            if isinstance(t, dict) and t.get("animal"):
                                if (not t.get("fed_today", False) and state.shed.get("WHEAT", 0) > 0) or t.get("yield_units", 0) > 0 or t.get("fertilizer_available", False):
                                    best_target = l_pos
                                    break

                # Priority 1: Urgent water (prevent withering)
                if not best_target and day < 27:
                    p0 = [p for p in urgent_water if p not in assigned_targets]
                    if p0:
                        best_target = min(p0, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 2: Ready harvests
                if not best_target:
                    p1_local = [p for p in harvestable if p not in assigned_targets and state.get_quadrant_for_pos(*p) == assigned_quad]
                    p1_any = [p for p in harvestable if p not in assigned_targets]
                    p1 = p1_local if p1_local else p1_any
                    if p1:
                        best_target = min(p1, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 3: CLEAR WEEDS in assigned quadrant
                if not best_target and weeds:
                    p_weed_local = [p for p in weeds if p not in assigned_targets and state.get_quadrant_for_pos(*p) == assigned_quad]
                    p_weed_any = [p for p in weeds if p not in assigned_targets]
                    p_weed = p_weed_local if p_weed_local else p_weed_any
                    if p_weed:
                        best_target = min(p_weed, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 4: EMPTY TILES in assigned quadrant (Plant 100% of the 25 squares!)
                if not best_target and day <= 25 and sum(available_seeds.values()) > 0:
                    p3_local = [p for p in empty if p not in assigned_targets and state.get_quadrant_for_pos(*p) == assigned_quad]
                    p3_any = [p for p in empty if p not in assigned_targets]
                    p3 = p3_local if p3_local else p3_any
                    if p3:
                        best_target = min(p3, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 5: Routine daily water
                if not best_target and day < 27:
                    p2_local = [p for p in routine_water if p not in assigned_targets and state.get_quadrant_for_pos(*p) == assigned_quad]
                    p2_any = [p for p in routine_water if p not in assigned_targets]
                    p2 = p2_local if p2_local else p2_any
                    if p2:
                        best_target = min(p2, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

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
