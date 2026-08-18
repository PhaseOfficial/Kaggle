"""
Master Industrial & Livestock Farm Agent for Kaggriculture.
High-Yield Standalone Submission with Dynamic Fibonacci Workforce Allocation.
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

LIVESTOCK_PLOTS = {
    "NW": {
        (4, 3): ("PASTURE", "COW"),     # 1 step North of Shed (4, 4)
        (3, 4): ("PASTURE", "COW"),     # 1 step West of Shed (4, 4)
        (3, 3): ("PASTURE", "SHEEP"),   # 1 step Northwest of Shed (4, 4)
        (2, 4): ("PASTURE", "SHEEP"),   # 2 steps West of Shed (4, 4)
    },
    "NE": {},
    "SW": {},
    "SE": {},
}

NW_WHEAT_TILES = {(1, 4), (0, 4), (4, 1), (4, 0), (2, 3), (1, 3), (3, 2)}
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

FIBONACCI_COSTS = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377]


def get_hire_cost(n: int) -> int:
    """Returns the Fibonacci hiring cost for the n-th hand today (0-indexed)."""
    if n < len(FIBONACCI_COSTS):
        return FIBONACCI_COSTS[n]
    a, b = FIBONACCI_COSTS[-2], FIBONACCI_COSTS[-1]
    for _ in range(n - len(FIBONACCI_COSTS) + 1):
        a, b = b, a + b
    return b


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


def get_price(product: str, inv: int, market_params: dict = None) -> int:
    params = (market_params or MARKET_PARAMS).get(product)
    if not params: return 1
    base = params["base"]
    I0 = params.get("I0", MARKET_I0)
    T = params["T"]

    if inv == I0: return base
    if inv < I0:
        func_name = params["below_func"]
        target = params["below_target"]
        delta = I0 - inv
        f_T = shape_func(func_name, T, T)
        amp = (target * base) / f_T if f_T > 0 else 0.0
        f_val = shape_func(func_name, delta, T)
        raw_price = base + amp * f_val
    else:
        func_name = params["above_func"]
        target = params["above_target"]
        delta = inv - I0
        f_T = shape_func(func_name, T, T)
        amp = (target * base) / f_T if f_T > 0 else 0.0
        f_val = shape_func(func_name, delta, T)
        raw_price = base - amp * f_val

    return max(PRICE_FLOOR, round(raw_price))


def get_safe_sell_quantity(
    product: str,
    current_inv: int,
    available_in_shed: int,
    remaining_days: int = 30,
    min_acceptable_price_ratio: float = 0.5,
) -> int:
    if available_in_shed <= 0: return 0
    params = MARKET_PARAMS.get(product, {})
    base = params.get("base", 1)
    min_price = max(PRICE_FLOOR, int(base * min_acceptable_price_ratio))

    if remaining_days <= 2:
        return min(available_in_shed, 100)

    if product in ("WHEAT", "EGG"):
        return min(available_in_shed, 20)

    safe_q = 0
    test_inv = current_inv
    for _ in range(min(available_in_shed, 15)):
        p = get_price(product, test_inv)
        if p < min_price: break
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
        self.market_prices = market.get("prices", {}) or {}

        town = obs.get("town", {}) or {}
        self.unlocked_shops = town.get("unlocked_shops", [])
        self.board_size = len(self.tiles) if self.tiles else 10

    def is_tile_unlocked(self, x: int, y: int) -> bool:
        if x < 0 or x >= self.board_size or y < 0 or y >= self.board_size: return False
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
        livestock_plots = set(LIVESTOCK_PLOTS.get("NW", {}).keys())
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

    def get_unfertilized_premium_tiles(self) -> list[tuple[int, int]]:
        unfertilized = []
        for x, y in self.get_all_unlocked_coords():
            t = self.get_tile(x, y)
            if isinstance(t, dict) and t.get("kind") == "PLANT":
                crop = t.get("crop")
                if crop in ("MELON", "STRAWBERRY", "TOMATO"):
                    if t.get("fertilized_until_day", 0) <= self.day:
                        unfertilized.append((x, y))
        return unfertilized

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
    # 1. Day 28 Whole-Farm Wheat Blitz (Empty tiles only): 2-day fast turnover harvest on Day 30!
    if day == 28:
        return "WHEAT"

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
        # Determine optimal workforce count based on farm scale and pending harvest volume
        base_hires = 5 if num_quads == 1 else (7 if num_quads == 2 else 9)
        harvestable_count = len(self.state.get_harvestable_tiles())

        # Surge hiring on heavy harvest days
        if harvestable_count >= 15 and money >= 1000:
            base_hires = min(base_hires + 1, 10)
        if harvestable_count >= 25 and money >= 3000:
            base_hires = min(base_hires + 1, 11)

        # Early day protection: Cap at 5 hands ($12 total daily wage)
        if day <= 3:
            base_hires = min(base_hires, 5)
        elif money < 300:
            base_hires = min(base_hires, 5)

        # Execute Fibonacci hires one by one checking exact marginal cost
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
                remaining_days=rem_days,
            )

            if safe_qty > 0:
                orders.append(["SELL", product, safe_qty])

        return orders[:max_orders]


class MultiWorkerDispatcher:
    def __init__(self, state: FarmState):
        self.state = state
        self.workers = [self.state.farmer_pos] + self.state.hands_pos
        self.unlocked_set = set(self.state.get_all_unlocked_coords())

    def dispatch(self) -> tuple[list, list]:
        day = self.state.day
        rem_days = self.state.remaining_days

        active_livestock = dict(LIVESTOCK_PLOTS["NW"])

        urgent_water = set(self.state.get_urgent_water_tiles())
        routine_water = set(self.state.get_routine_water_tiles())
        unfertilized_premium = set(self.state.get_unfertilized_premium_tiles())
        harvestable = set(self.state.get_harvestable_tiles())
        weeds = set(self.state.get_weed_tiles())
        empty = set(self.state.get_empty_tiles())

        active_quads_list = sorted(list(self.state.unlocked_quadrants))
        worker_quad_map = {}
        for w_idx in range(len(self.workers)):
            if w_idx == 0:
                worker_quad_map[w_idx] = "NW"
            else:
                worker_quad_map[w_idx] = active_quads_list[(w_idx - 1) % len(active_quads_list)]

        assigned_targets = set()
        fed_animals_today = set()
        fertilized_today = set()
        worker_actions = []
        available_seeds = dict(self.state.seeds)

        for w_idx, w_pos in enumerate(self.workers):
            tile = self.state.get_tile(*w_pos)
            action = None
            assigned_quad = worker_quad_map.get(w_idx, "NW")
            inv_w = self.state.inventories[w_idx] if w_idx < len(self.state.inventories) else {}
            has_fert = inv_w.get("FERTILIZER", 0) > 0

            # --- A. Farmer Special: Setup animals & Feed Pickup ---
            if w_idx == 0 and day <= 28:
                has_animal_in_inv = any(inv_w.get(a, 0) > 0 for a in ["COW", "SHEEP"])
                has_animal_in_shed = any(self.state.shed.get(a, 0) > 0 for a in ["COW", "SHEEP"])
                needs_feed_count = sum(1 for p in active_livestock if isinstance(self.state.get_tile(*p), dict) and self.state.get_tile(*p).get("animal") and not self.state.get_tile(*p).get("fed_today", False))

                if not has_animal_in_inv and has_animal_in_shed:
                    if w_pos == (4, 4):
                        for anim in ["COW", "SHEEP"]:
                            if self.state.shed.get(anim, 0) > 0:
                                action = ["PICKUP", anim, 1]
                                break
                    else:
                        step = get_bfs_step(w_pos, (4, 4), self.unlocked_set)
                        action = [step] if step != "PASS" else ["PASS"]

                elif has_animal_in_inv:
                    for pos, (struct, anim) in active_livestock.items():
                        if inv_w.get(anim, 0) > 0:
                            t_target = self.state.get_tile(*pos)
                            if t_target is None or (isinstance(t_target, dict) and t_target.get("animal") is None):
                                if w_pos != pos:
                                    step = get_bfs_step(w_pos, pos, self.unlocked_set)
                                    action = [step] if step != "PASS" else ["PASS"]
                                else:
                                    if tile is None:
                                        action = ["BUILD_PASTURE"]
                                    elif isinstance(tile, dict) and tile.get("animal") is None:
                                        action = ["PLACE", anim]
                                break

                elif w_pos == (4, 4) and needs_feed_count > 0 and inv_w.get("WHEAT", 0) < needs_feed_count and self.state.shed.get("WHEAT", 0) > 0:
                    pickup_n = min(needs_feed_count - inv_w.get("WHEAT", 0), self.state.shed.get("WHEAT", 0))
                    if pickup_n > 0:
                        action = ["PICKUP", "WHEAT", pickup_n]

            # --- B. Livestock Care on Standing Plot ---
            if action is None and w_pos in active_livestock and w_pos not in assigned_targets:
                req_struct, req_animal = active_livestock[w_pos]
                if isinstance(tile, dict) and tile.get("animal"):
                    if not tile.get("fed_today", False) and w_pos not in fed_animals_today and inv_w.get("WHEAT", 0) > 0:
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
                elif day <= 29 and w_pos in urgent_water and w_pos not in assigned_targets:
                    action = ["WATER"]
                    assigned_targets.add(w_pos)
                elif day <= 28 and has_fert and w_pos in unfertilized_premium and w_pos not in fertilized_today:
                    action = ["FERTILIZE"]
                    fertilized_today.add(w_pos)
                    assigned_targets.add(w_pos)
                elif day <= 29 and w_pos in routine_water and w_pos not in assigned_targets:
                    action = ["WATER"]
                    assigned_targets.add(w_pos)
                elif w_pos in empty and (day <= 25 or day == 28) and w_pos not in assigned_targets:
                    pref_crop = get_target_crop_for_pos(w_pos, rem_days, day)
                    chosen_crop = None
                    if pref_crop and available_seeds.get(pref_crop, 0) > 0:
                        chosen_crop = pref_crop
                    elif available_seeds.get("WHEAT", 0) > 0:
                        chosen_crop = "WHEAT"
                    elif available_seeds.get("STRAWBERRY", 0) > 0:
                        chosen_crop = "STRAWBERRY"
                    elif available_seeds.get("MELON", 0) > 0:
                        chosen_crop = "MELON"
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
                if day >= 30 or (day >= 26 and day != 28):
                    p_harv_local = [p for p in harvestable if p not in assigned_targets and self.state.get_quadrant_for_pos(*p) == assigned_quad]
                    p_harv_any = [p for p in harvestable if p not in assigned_targets]
                    p_harv = p_harv_local if p_harv_local else p_harv_any
                    if p_harv:
                        best_target = min(p_harv, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and w_idx == 0:
                    for l_pos in active_livestock:
                        if l_pos not in assigned_targets and l_pos not in fed_animals_today:
                            t = self.state.get_tile(*l_pos)
                            if isinstance(t, dict) and t.get("animal"):
                                if (not t.get("fed_today", False) and self.state.shed.get("WHEAT", 0) > 0) or t.get("yield_units", 0) > 0 or t.get("fertilizer_available", False):
                                    best_target = l_pos
                                    break

                if not best_target and day <= 29:
                    p0 = [p for p in urgent_water if p not in assigned_targets]
                    if p0:
                        best_target = min(p0, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target:
                    p1_local = [p for p in harvestable if p not in assigned_targets and self.state.get_quadrant_for_pos(*p) == assigned_quad]
                    p1_any = [p for p in harvestable if p not in assigned_targets]
                    p1 = p1_local if p1_local else p1_any
                    if p1:
                        best_target = min(p1, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and has_fert and day <= 27:
                    p_fert_local = [p for p in unfertilized_premium if p not in assigned_targets and p not in fertilized_today and self.state.get_quadrant_for_pos(*p) == assigned_quad]
                    p_fert_any = [p for p in unfertilized_premium if p not in assigned_targets and p not in fertilized_today]
                    p_fert = p_fert_local if p_fert_local else p_fert_any
                    if p_fert:
                        best_target = min(p_fert, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and weeds:
                    p_weed_local = [p for p in weeds if p not in assigned_targets and self.state.get_quadrant_for_pos(*p) == assigned_quad]
                    p_weed_any = [p for p in weeds if p not in assigned_targets]
                    p_weed = p_weed_local if p_weed_local else p_weed_any
                    if p_weed:
                        best_target = min(p_weed, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and (day <= 25 or day == 28) and sum(available_seeds.values()) > 0:
                    p3_local = [p for p in empty if p not in assigned_targets and self.state.get_quadrant_for_pos(*p) == assigned_quad]
                    p3_any = [p for p in empty if p not in assigned_targets]
                    p3 = p3_local if p3_local else p3_any
                    if p3:
                        best_target = min(p3, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and day <= 29:
                    p2_local = [p for p in routine_water if p not in assigned_targets and self.state.get_quadrant_for_pos(*p) == assigned_quad]
                    p2_any = [p for p in routine_water if p not in assigned_targets]
                    p2 = p2_local if p2_local else p2_any
                    if p2:
                        best_target = min(p2, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if best_target and best_target != w_pos:
                    assigned_targets.add(best_target)
                    step = get_bfs_step(w_pos, best_target, self.unlocked_set)
                    action = [step] if step != "PASS" else ["PASS"]
                else:
                    action = ["PASS"]

            worker_actions.append(action)

        farmer_action = worker_actions[0] if worker_actions else ["PASS"]
        hands_actions = worker_actions[1:] if len(worker_actions) > 1 else []

        return farmer_action, hands_actions


def agent(obs: dict) -> dict:
    """
    Kaggriculture agent decision function.
    Returns: {"farmer": [...], "hands": [...], "market": [...]}
    """
    try:
        state = FarmState(obs)
        planner = ZonalMacroPlanner(state)
        market_orders = planner.plan_market_orders()
        dispatcher = MultiWorkerDispatcher(state)
        farmer_action, hands_actions = dispatcher.dispatch()

        return {
            "farmer": farmer_action,
            "hands": hands_actions,
            "market": market_orders,
        }
    except Exception as e:
        print(f"Agent error at step {obs.get('step')}: {e}")
        return {"farmer": ["PASS"], "hands": [], "market": []}
