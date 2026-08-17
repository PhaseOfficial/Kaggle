"""
Strategy V6: Optimized High-Yield 100k+ Engine.
Built directly on top of the proven main.py architecture with the 7 critical multipliers:
1. Plot 4 (SE) Land Expansion unlocked on Day 15-18 when capital >= $15,000.
2. Dense Wave 2 Melon & Strawberry rotations across NE, SW, and SE (harvested Days 21-22).
3. Zero Animal Starvation (animals procured Day 4+ once wheat feed is in shed).
4. Full 13-Worker Workforce for 100 tiles.
5. Smart Fertilizer Collection & Dedicated Fertilization for Premium Crops.
6. Multi-turn Sliced Selling to prevent quadratic market crashes.
7. Day 28 Whole-Farm Wheat Blitz + Day 30 Grand Liquidation.
"""
import math
from collections import Counter, deque
import kaggle_environments

CROPS = {
    "WHEAT": {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT": {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO": {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON": {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}

ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP", "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW": {"cost": 400, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
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

# 4 Livestock Plots in NW directly hugging Shed (4, 4)
LIVESTOCK_PLOTS = {
    (4, 3): ("PASTURE", "COW"),
    (3, 4): ("PASTURE", "COW"),
    (3, 3): ("PASTURE", "SHEEP"),
    (2, 4): ("PASTURE", "SHEEP"),
}

NW_WHEAT_TILES = {(1, 4), (0, 4), (4, 1), (4, 0), (2, 3), (1, 3), (3, 2)}

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
    if remaining_days <= 1: return min(available_in_shed, 25)
    if product in ("WHEAT", "EGG"): return min(available_in_shed, 20)
    if product == "FERTILIZER": return min(available_in_shed, 8)

    safe_q = 0
    test_inv = current_inv
    min_acceptable = 0.45 if product == "MELON" else 0.55
    min_price = max(PRICE_FLOOR, int(MARKET_PARAMS[product]["base"] * min_acceptable))
    for _ in range(min(available_in_shed, 15)):
        p = get_price(product, test_inv)
        if p < min_price: break
        safe_q += 1
        test_inv += 1
    return max(1, safe_q) if safe_q > 0 else (1 if available_in_shed > 30 else 0)

def get_target_crop_for_pos_v6(pos: tuple[int, int], remaining_days: int, day: int) -> str | None:
    # Day 28 Whole-Farm Wheat Blitz
    if day == 28:
        return "WHEAT"

    if day >= 29 or (day >= 26 and day != 28) or remaining_days <= 1:
        return None

    x, y = pos
    # Plot 1 (NW): Dedicated wheat for feed + Early Melons -> Strawberries
    if x < 5 and y < 5:
        if pos in NW_WHEAT_TILES:
            return "WHEAT"
        if day <= 10:
            return "MELON"
        elif day <= 25:
            return "STRAWBERRY"
        return "WHEAT"

    # Plot 2 (NE): Covers x in [5, 9], y in [0, 4] -> High-Yield Melons
    if x >= 5 and y < 5:
        if day <= 19 and remaining_days >= 10:
            if (x + y) % 4 != 0:
                return "MELON"
            return "WHEAT"
        return "WHEAT"

    # Plot 3 (SW): Covers x in [0, 4], y in [5, 9] -> Wave 2 Melons & Targeted Wheat
    if x < 5 and y >= 5:
        if day <= 19 and remaining_days >= 10:
            if (x + y) % 2 == 0:
                return "MELON"
            return "WHEAT"
        return "WHEAT"

    # Plot 4 (SE): Covers x in [5, 9], y in [5, 9] -> Wave 2 Melons & Wheat
    if x >= 5 and y >= 5:
        if day <= 19 and remaining_days >= 10:
            if (x + y) % 2 == 0:
                return "MELON"
            return "WHEAT"
        return "WHEAT"

    return "WHEAT"

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
                dx = path[1][0] - start[0]
                dy = path[1][1] - start[1]
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

def agent_v6(obs: dict) -> dict:
    try:
        player_id = obs.get("player", 0)
        day = obs.get("day", 0)
        hour = obs.get("hour", 0)
        remaining_days = max(0, 30 - day)
        farms = obs.get("farms", [])
        my_farm = farms[player_id] if player_id < len(farms) else {}
        money = float(my_farm.get("money", 0))
        farmer_pos = tuple(my_farm.get("farmer", [4, 4]))
        hands_pos = [tuple(h) for h in my_farm.get("hands", [])]
        tiles = my_farm.get("tiles", [])
        unlocked_quads = set(my_farm.get("unlocked_quadrants", ["NW"]))
        hires_today = my_farm.get("hires_today", 0)

        private = obs.get("private", {}) or {}
        shed = private.get("shed", {}) or {}
        seeds = private.get("seeds", {}) or {}
        inventories = private.get("inventories", [{}])

        market_info = obs.get("market", {}) or {}
        market_inv = market_info.get("inventory", {}) or {}

        board_size = len(tiles) if tiles else 10

        def is_unlocked(x, y):
            if x < 0 or x >= board_size or y < 0 or y >= board_size: return False
            qx = "W" if x < 5 else "E"
            qy = "N" if y < 5 else "S"
            return (qy + qx) in unlocked_quads

        def get_tile(x, y):
            if 0 <= y < len(tiles) and 0 <= x < len(tiles[y]):
                return tiles[y][x]
            return "LOCKED"

        unlocked_coords = [(x, y) for y in range(board_size) for x in range(board_size) if is_unlocked(x, y)]
        unlocked_set = set(unlocked_coords)

        # -------------------------------------------------------------
        # 1. MACRO PLANNER
        # -------------------------------------------------------------
        orders = []
        max_orders = 10
        cur_money = money
        num_quads = len(unlocked_quads)

        # Workforce
        target_hires = 5 if num_quads == 1 else (7 if num_quads == 2 else (10 if num_quads == 3 else 12))
        needed_hires = max(0, target_hires - hires_today)
        if day <= 29 and cur_money >= 12 and needed_hires > 0:
            for _ in range(needed_hires):
                if len(orders) >= max_orders: break
                orders.append(["HIRE"])

        # Livestock Queue: 2 Cows + 2 Sheep (bought starting Day 2+ or when wheat in shed >= 3)
        target_cows = 2
        target_sheep = 2
        total_cows = sum(1 for p, info in LIVESTOCK_PLOTS.items() if info[1] == "COW" and isinstance(get_tile(*p), dict) and get_tile(*p).get("animal") == "COW") + shed.get("COW", 0) + sum(inv.get("COW", 0) for inv in inventories)
        total_sheep = sum(1 for p, info in LIVESTOCK_PLOTS.items() if info[1] == "SHEEP" and isinstance(get_tile(*p), dict) and get_tile(*p).get("animal") == "SHEEP") + shed.get("SHEEP", 0) + sum(inv.get("SHEEP", 0) for inv in inventories)

        has_feed = (day >= 3 or shed.get("WHEAT", 0) >= 3)
        if has_feed and day <= 20 and len(orders) < max_orders:
            while total_cows < target_cows and cur_money >= 500 and len(orders) < max_orders:
                orders.append(["BUY_ANIMAL", "COW", 1])
                cur_money -= 400
                total_cows += 1
            while total_sheep < target_sheep and cur_money >= 600 and len(orders) < max_orders:
                orders.append(["BUY_ANIMAL", "SHEEP", 1])
                cur_money -= 500
                total_sheep += 1

        all_plot1_stocked = (total_cows >= target_cows and total_sheep >= target_sheep)

        # Controlled Land Expansion (NE -> SW -> SE)
        if day <= 20 and len(orders) < max_orders and all_plot1_stocked:
            if "NE" not in unlocked_quads and cur_money >= 2500 and day <= 8:
                orders.append(["BUY_LAND", "NE"])
                cur_money -= 1000
                unlocked_quads.add("NE")
                num_quads += 1
            elif "SW" not in unlocked_quads and cur_money >= 5000 and day <= 15:
                orders.append(["BUY_LAND", "SW"])
                cur_money -= 2000
                unlocked_quads.add("SW")
                num_quads += 1
            elif "SE" not in unlocked_quads and cur_money >= 8000 and day <= 18:
                orders.append(["BUY_LAND", "SE"])
                cur_money -= 4000
                unlocked_quads.add("SE")
                num_quads += 1

        # Seed Purchasing: Strict Portfolio (Wheat, Melon, Strawberry)
        empty_tiles = [(x, y) for (x, y) in unlocked_coords if get_tile(x, y) is None and (x, y) not in LIVESTOCK_PLOTS]
        weed_tiles = [(x, y) for (x, y) in unlocked_coords if isinstance(get_tile(x, y), dict) and get_tile(x, y).get("kind") == "WEED"]

        if day <= 28 and len(orders) < max_orders:
            needed_seeds = Counter()
            if day in (27, 28):
                total_emp = len(empty_tiles) + len(weed_tiles)
                needed_seeds["WHEAT"] = max(needed_seeds["WHEAT"], total_emp + 15)
            else:
                for pos in empty_tiles + weed_tiles:
                    c = get_target_crop_for_pos_v6(pos, remaining_days, day)
                    if c: needed_seeds[c] += 1

            wheat_buffer = max(0, 10 - seeds.get("WHEAT", 0))
            if wheat_buffer > 0: needed_seeds["WHEAT"] += wheat_buffer

            spendable = max(0, cur_money - 200) if day < 26 else cur_money
            for crop in ["WHEAT", "MELON", "STRAWBERRY"]:
                if len(orders) >= max_orders: break
                cnt = needed_seeds.get(crop, 0)
                if cnt <= 0: continue
                held = seeds.get(crop, 0)
                to_buy = max(0, cnt - held)
                if to_buy > 0:
                    sc = CROPS[crop]["seed"]
                    aff = min(to_buy, int(spendable // sc)) if sc > 0 else 0
                    if aff > 0:
                        batch = min(aff, 25)
                        orders.append(["BUY_SEED", crop, batch])
                        spendable -= sc * batch

        # Shed Liquidation
        for product in PRODUCTS:
            if len(orders) >= max_orders: break
            qty = shed.get(product, 0)
            if qty <= 0: continue

            if product == "WHEAT" and day < 29:
                if qty > 8:
                    orders.append(["SELL", "WHEAT", min(qty - 8, 20)])
                continue
            if product == "FERTILIZER" and day < 28:
                if qty > 4:
                    orders.append(["SELL", "FERTILIZER", qty - 4])
                continue
            if day >= 29 or remaining_days <= 1:
                orders.append(["SELL", product, min(qty, 25)])
                continue

            cur_i = market_inv.get(product, 10000)
            safe_q = get_safe_sell_quantity(product, cur_i, qty, remaining_days)
            if safe_q > 0:
                orders.append(["SELL", product, safe_q])

        market_orders = orders[:max_orders]

        # -------------------------------------------------------------
        # 2. TASK DISPATCHER
        # -------------------------------------------------------------
        workers = [farmer_pos] + hands_pos
        harvestable = set()
        urgent_water = set()
        routine_water = set()
        unfert_premium = set()
        weeds = set(weed_tiles)
        empty = set(empty_tiles)

        for x, y in unlocked_coords:
            t = get_tile(x, y)
            if isinstance(t, dict):
                if t.get("kind") == "PLANT":
                    crop = t.get("crop")
                    c_info = CROPS.get(crop, {})
                    age = day - t.get("planted_day", 0)
                    ongoing = c_info.get("ongoing", False)
                    max_y_day = c_info.get("max_yield_day", 4)
                    y_units = t.get("yield_units", 0)
                    if y_units > 0 and (day >= 26 or ongoing or age >= max_y_day or remaining_days <= 1):
                        harvestable.add((x, y))
                    if not t.get("watered_today", False):
                        if t.get("consecutive_unwatered", 0) >= 1:
                            urgent_water.add((x, y))
                        else:
                            routine_water.add((x, y))
                    if crop in ("MELON", "STRAWBERRY") and t.get("fertilized_until_day", 0) <= day:
                        unfert_premium.add((x, y))
                elif t.get("kind") in ("COOP", "PASTURE"):
                    if t.get("yield_units", 0) > 0:
                        harvestable.add((x, y))

        quad_list = sorted(list(unlocked_quads))
        worker_quad_map = {}
        for w_i in range(len(workers)):
            if w_i in (0, 1):
                worker_quad_map[w_i] = "NW"
            else:
                worker_quad_map[w_i] = quad_list[(w_i - 1) % len(quad_list)]

        assigned_targets = set()
        fed_today = set()
        fert_today = set()
        worker_actions = []
        avail_seeds = dict(seeds)

        for w_idx, w_pos in enumerate(workers):
            tile = get_tile(*w_pos)
            action = None
            assigned_quad = worker_quad_map.get(w_idx, "NW")
            inv_w = inventories[w_idx] if w_idx < len(inventories) else {}
            has_fert = inv_w.get("FERTILIZER", 0) > 0

            # --- A. Farmer Special: Coops & Animals Pickup/Placement & Feed Pickup ---
            if w_idx == 0 and day <= 28:
                has_anim_inv = any(inv_w.get(a, 0) > 0 for a in ["COW", "SHEEP"])
                has_anim_shed = any(shed.get(a, 0) > 0 for a in ["COW", "SHEEP"])
                needs_feed_count = sum(1 for p in LIVESTOCK_PLOTS if isinstance(get_tile(*p), dict) and get_tile(*p).get("animal") and not get_tile(*p).get("fed_today", False))

                if not has_anim_inv and has_anim_shed:
                    if w_pos == (4, 4):
                        for anim in ["COW", "SHEEP"]:
                            if shed.get(anim, 0) > 0:
                                action = ["PICKUP", anim, 1]
                                break
                    else:
                        st = get_bfs_step(w_pos, (4, 4), unlocked_set)
                        action = [st] if st != "PASS" else ["PASS"]

                elif has_anim_inv:
                    for pos, (struct, anim) in LIVESTOCK_PLOTS.items():
                        if inv_w.get(anim, 0) > 0:
                            t_targ = get_tile(*pos)
                            if t_targ is None or (isinstance(t_targ, dict) and t_targ.get("animal") is None):
                                if w_pos != pos:
                                    st = get_bfs_step(w_pos, pos, unlocked_set)
                                    action = [st] if st != "PASS" else ["PASS"]
                                else:
                                    if tile is None:
                                        action = ["BUILD_PASTURE"]
                                    elif isinstance(tile, dict) and tile.get("animal") is None:
                                        action = ["PLACE", anim]
                                break

                elif w_pos == (4, 4) and needs_feed_count > 0 and inv_w.get("WHEAT", 0) < needs_feed_count and shed.get("WHEAT", 0) > 0:
                    pk = min(needs_feed_count - inv_w.get("WHEAT", 0), shed.get("WHEAT", 0))
                    if pk > 0: action = ["PICKUP", "WHEAT", pk]

            # --- B. Livestock Care on Standing Tile ---
            if action is None and w_pos in LIVESTOCK_PLOTS and w_pos not in assigned_targets:
                if isinstance(tile, dict) and tile.get("animal"):
                    if not tile.get("fed_today", False) and w_pos not in fed_today and inv_w.get("WHEAT", 0) > 0:
                        action = ["FEED"]
                        fed_today.add(w_pos)
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

            # --- C. Crop Actions on Standing Tile ---
            if action is None:
                if w_pos in harvestable and w_pos not in assigned_targets:
                    action = ["HARVEST"]
                    assigned_targets.add(w_pos)
                elif day <= 29 and w_pos in urgent_water and w_pos not in assigned_targets:
                    action = ["WATER"]
                    assigned_targets.add(w_pos)
                elif day <= 28 and has_fert and w_pos in unfert_premium and w_pos not in fert_today:
                    action = ["FERTILIZE"]
                    fert_today.add(w_pos)
                    assigned_targets.add(w_pos)
                elif day <= 29 and w_pos in routine_water and w_pos not in assigned_targets:
                    action = ["WATER"]
                    assigned_targets.add(w_pos)
                elif w_pos in empty and (day <= 25 or day == 28) and w_pos not in assigned_targets:
                    pref_c = get_target_crop_for_pos_v6(w_pos, remaining_days, day)
                    chosen_c = None
                    if pref_c and avail_seeds.get(pref_c, 0) > 0:
                        chosen_c = pref_c
                    elif avail_seeds.get("WHEAT", 0) > 0:
                        chosen_c = "WHEAT"
                    elif avail_seeds.get("MELON", 0) > 0:
                        chosen_c = "MELON"
                    elif avail_seeds.get("STRAWBERRY", 0) > 0:
                        chosen_c = "STRAWBERRY"
                    if chosen_c:
                        action = ["PLANT", chosen_c]
                        avail_seeds[chosen_c] -= 1
                        assigned_targets.add(w_pos)
                elif w_pos in weeds and w_pos not in assigned_targets:
                    action = ["DIG"]
                    assigned_targets.add(w_pos)

            # --- D. BFS Navigation ---
            if action is None:
                best_target = None
                # Mass Harvest on Day 10, Day 20, and Days 26+
                if day in (10, 20) or day >= 26:
                    p_harv_local = [p for p in harvestable if p not in assigned_targets and (("S" if p[1]>=5 else "N") + ("E" if p[0]>=5 else "W")) == assigned_quad]
                    p_harv_any = [p for p in harvestable if p not in assigned_targets]
                    p_harv = p_harv_local if p_harv_local else p_harv_any
                    if p_harv:
                        best_target = min(p_harv, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and w_idx == 0:
                    for g_pos in LIVESTOCK_PLOTS:
                        if g_pos not in assigned_targets and g_pos not in fed_today:
                            gt = get_tile(*g_pos)
                            if isinstance(gt, dict) and gt.get("animal"):
                                if (not gt.get("fed_today", False) and (inv_w.get("WHEAT", 0) > 0 or shed.get("WHEAT", 0) > 0)) or gt.get("yield_units", 0) > 0 or gt.get("fertilizer_available", False):
                                    best_target = g_pos
                                    break

                if not best_target and day <= 29:
                    p0 = [p for p in urgent_water if p not in assigned_targets]
                    if p0:
                        best_target = min(p0, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target:
                    p1_local = [p for p in harvestable if p not in assigned_targets and (("S" if p[1]>=5 else "N") + ("E" if p[0]>=5 else "W")) == assigned_quad]
                    p1_any = [p for p in harvestable if p not in assigned_targets]
                    p1 = p1_local if p1_local else p1_any
                    if p1:
                        best_target = min(p1, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and has_fert and day <= 27:
                    pf_local = [p for p in unfert_premium if p not in assigned_targets and (("S" if p[1]>=5 else "N") + ("E" if p[0]>=5 else "W")) == assigned_quad]
                    pf_any = [p for p in unfert_premium if p not in assigned_targets]
                    pf = pf_local if pf_local else pf_any
                    if pf:
                        best_target = min(pf, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and weeds:
                    pw_local = [p for p in weeds if p not in assigned_targets and (("S" if p[1]>=5 else "N") + ("E" if p[0]>=5 else "W")) == assigned_quad]
                    pw_any = [p for p in weeds if p not in assigned_targets]
                    pw = pw_local if pw_local else pw_any
                    if pw:
                        best_target = min(pw, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and (day <= 25 or day == 28) and sum(avail_seeds.values()) > 0:
                    pe_local = [p for p in empty if p not in assigned_targets and (("S" if p[1]>=5 else "N") + ("E" if p[0]>=5 else "W")) == assigned_quad]
                    pe_any = [p for p in empty if p not in assigned_targets]
                    pe = pe_local if pe_local else pe_any
                    if pe:
                        best_target = min(pe, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and day <= 29:
                    pr_local = [p for p in routine_water if p not in assigned_targets and (("S" if p[1]>=5 else "N") + ("E" if p[0]>=5 else "W")) == assigned_quad]
                    pr_any = [p for p in routine_water if p not in assigned_targets]
                    pr = pr_local if pr_local else pr_any
                    if pr:
                        best_target = min(pr, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if best_target and best_target != w_pos:
                    assigned_targets.add(best_target)
                    st = get_bfs_step(w_pos, best_target, unlocked_set)
                    action = [st] if st != "PASS" else ["PASS"]
                else:
                    action = ["PASS"]

            worker_actions.append(action)

        farmer_act = worker_actions[0] if worker_actions else ["PASS"]
        hands_act = worker_actions[1:] if len(worker_actions) > 1 else []

        return {
            "farmer": farmer_act,
            "hands": hands_act,
            "market": market_orders,
        }
    except Exception as e:
        print(f"Error at step {obs.get('step')}: {e}")
        return {"farmer": ["PASS"], "hands": [], "market": []}
