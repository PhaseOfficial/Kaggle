"""
Test and benchmark script for testing high-yield 100k+ strategy.
"""
import math
import time
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

# 8 Goose Coops hugging Shed (4, 4) in Plot 1 (NW)
GOOSE_COOPS = {
    (4, 3): ("COOP", "GOOSE"),
    (3, 4): ("COOP", "GOOSE"),
    (3, 3): ("COOP", "GOOSE"),
    (2, 4): ("COOP", "GOOSE"),
    (4, 2): ("COOP", "GOOSE"),
    (2, 3): ("COOP", "GOOSE"),
    (1, 4): ("COOP", "GOOSE"),
    (3, 2): ("COOP", "GOOSE"),
}

NW_WHEAT_COORDS = {(4, 1), (4, 0), (3, 1), (3, 0), (2, 2), (1, 3), (0, 4), (0, 3)}

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
    if remaining_days <= 2: return available_in_shed
    if product in ("WHEAT", "EGG"): return min(available_in_shed, 25)
    if product == "FERTILIZER": return min(available_in_shed, 15)
    # For Melons, Strawberries, Carrots
    safe_q = 0
    test_inv = current_inv
    min_acceptable = 0.4 if product == "MELON" else 0.5
    min_price = max(PRICE_FLOOR, int(MARKET_PARAMS[product]["base"] * min_acceptable))
    for _ in range(min(available_in_shed, 20)):
        p = get_price(product, test_inv)
        if p < min_price: break
        safe_q += 1
        test_inv += 1
    return max(1, safe_q) if safe_q > 0 else (1 if available_in_shed > 40 else 0)

def get_target_crop(pos: tuple[int, int], day: int, remaining_days: int) -> str | None:
    if day == 28:
        return "WHEAT"
    if day >= 29 or (day >= 26 and day != 28) or remaining_days <= 1:
        return None

    x, y = pos
    # NW (Plot 1)
    if x < 5 and y < 5:
        if pos in NW_WHEAT_COORDS:
            return "WHEAT"
        if day <= 8:
            return "MELON"
        elif day <= 24:
            return "STRAWBERRY"
        return "WHEAT"

    # NE (Plot 2): High-yield Melon & Carrot engine
    if x >= 5 and y < 5:
        if day <= 18:
            if (x + y) % 3 == 0:
                return "STRAWBERRY" if day <= 10 else "CARROT"
            return "MELON"
        elif day <= 25:
            return "CARROT" if (x + y) % 2 == 0 else "WHEAT"
        return "WHEAT"

    # SW (Plot 3): Melons & Carrots
    if x < 5 and y >= 5:
        if day <= 18:
            return "MELON" if (x + y) % 2 == 0 else "CARROT"
        elif day <= 25:
            return "CARROT"
        return "WHEAT"

    # SE (Plot 4): Melons & Carrots
    if x >= 5 and y >= 5:
        if day <= 18:
            return "MELON" if (x + y) % 2 == 0 else "CARROT"
        elif day <= 25:
            return "CARROT"
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

def fast_agent(obs: dict) -> dict:
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
        # 1. MARKET & MACRO PLANNER
        # -------------------------------------------------------------
        orders = []
        max_orders = 10
        cur_money = money
        num_quads = len(unlocked_quads)

        # A. WORKFORCE HIRING
        target_hires = 5 if num_quads == 1 else (8 if num_quads == 2 else (10 if num_quads == 3 else 12))
        needed_hires = max(0, target_hires - hires_today)
        if day <= 29 and cur_money >= 12 and needed_hires > 0:
            for _ in range(needed_hires):
                if len(orders) >= max_orders: break
                orders.append(["HIRE"])

        # B. EARLY LAND EXPANSION
        # Day 0: Buy NE immediately!
        if len(orders) < max_orders:
            if "NE" not in unlocked_quads and cur_money >= 1000 and day <= 5:
                orders.append(["BUY_LAND", "NE"])
                cur_money -= 1000
                unlocked_quads.add("NE")
                num_quads += 1
            elif "SW" not in unlocked_quads and cur_money >= 3500 and day <= 12:
                orders.append(["BUY_LAND", "SW"])
                cur_money -= 2000
                unlocked_quads.add("SW")
                num_quads += 1
            elif "SE" not in unlocked_quads and cur_money >= 6000 and day <= 18:
                orders.append(["BUY_LAND", "SE"])
                cur_money -= 4000
                unlocked_quads.add("SE")
                num_quads += 1

        # C. GOOSE PROCUREMENT (8 Geese in NW)
        target_geese = 8
        total_geese = sum(1 for p in GOOSE_COOPS if isinstance(get_tile(*p), dict) and get_tile(*p).get("animal") == "GOOSE") + shed.get("GOOSE", 0) + sum(inv.get("GOOSE", 0) for inv in inventories)
        if day <= 10 and len(orders) < max_orders:
            while total_geese < target_geese and cur_money >= 350 and len(orders) < max_orders:
                orders.append(["BUY_ANIMAL", "GOOSE", 1])
                cur_money -= 300
                total_geese += 1

        # D. SEED PURCHASING
        empty_tiles = [(x, y) for (x, y) in unlocked_coords if get_tile(x, y) is None and (x, y) not in GOOSE_COOPS]
        weed_tiles = [(x, y) for (x, y) in unlocked_coords if isinstance(get_tile(x, y), dict) and get_tile(x, y).get("kind") == "WEED"]

        if day <= 28 and len(orders) < max_orders:
            needed_seeds = Counter()
            if day in (27, 28):
                total_emp = len(empty_tiles) + len(weed_tiles)
                needed_seeds["WHEAT"] = max(needed_seeds["WHEAT"], total_emp + 15)
            else:
                for pos in empty_tiles + weed_tiles:
                    c = get_target_crop(pos, day, remaining_days)
                    if c: needed_seeds[c] += 1

            # Buffer wheat for geese feed
            wheat_buffer = max(0, 15 - seeds.get("WHEAT", 0))
            if wheat_buffer > 0: needed_seeds["WHEAT"] += wheat_buffer

            spendable = max(0, cur_money - 150) if day < 26 else cur_money
            for crop in ["WHEAT", "MELON", "STRAWBERRY", "CARROT"]:
                if len(orders) >= max_orders: break
                cnt = needed_seeds.get(crop, 0)
                if cnt <= 0: continue
                held = seeds.get(crop, 0)
                to_buy = max(0, cnt - held)
                if to_buy > 0:
                    sc = CROPS[crop]["seed"]
                    aff = min(to_buy, int(spendable // sc)) if sc > 0 else 0
                    if aff > 0:
                        batch = min(aff, 30)
                        orders.append(["BUY_SEED", crop, batch])
                        spendable -= sc * batch

        # E. SHED INVENTORY LIQUIDATION
        for product in PRODUCTS:
            if len(orders) >= max_orders: break
            qty = shed.get(product, 0)
            if qty <= 0: continue

            if product == "WHEAT" and day < 29:
                if qty > 10:
                    orders.append(["SELL", "WHEAT", min(qty - 10, 30)])
                continue
            if product == "FERTILIZER" and day < 27:
                if qty > 6:
                    orders.append(["SELL", "FERTILIZER", qty - 6])
                continue
            if day >= 29 or remaining_days <= 2:
                orders.append(["SELL", product, qty])
                continue

            cur_i = market_inv.get(product, 10000)
            safe_q = get_safe_sell_quantity(product, cur_i, qty, remaining_days)
            if safe_q > 0:
                orders.append(["SELL", product, safe_q])

        market_orders = orders[:max_orders]

        # -------------------------------------------------------------
        # 2. MULTI-WORKER TASK DISPATCHER
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
                has_anim_inv = inv_w.get("GOOSE", 0) > 0
                has_anim_shed = shed.get("GOOSE", 0) > 0
                needs_feed_count = sum(1 for p in GOOSE_COOPS if isinstance(get_tile(*p), dict) and get_tile(*p).get("animal") and not get_tile(*p).get("fed_today", False))

                if not has_anim_inv and has_anim_shed:
                    if w_pos == (4, 4):
                        action = ["PICKUP", "GOOSE", min(has_anim_shed, 4)]
                    else:
                        st = get_bfs_step(w_pos, (4, 4), unlocked_set)
                        action = [st] if st != "PASS" else ["PASS"]

                elif has_anim_inv:
                    for pos, (struct, anim) in GOOSE_COOPS.items():
                        t_targ = get_tile(*pos)
                        if t_targ is None or (isinstance(t_targ, dict) and t_targ.get("animal") is None):
                            if w_pos != pos:
                                st = get_bfs_step(w_pos, pos, unlocked_set)
                                action = [st] if st != "PASS" else ["PASS"]
                            else:
                                if tile is None:
                                    action = ["BUILD_COOP"]
                                elif isinstance(tile, dict) and tile.get("animal") is None:
                                    action = ["PLACE", "GOOSE"]
                            break

                elif w_pos == (4, 4) and needs_feed_count > 0 and inv_w.get("WHEAT", 0) < needs_feed_count and shed.get("WHEAT", 0) > 0:
                    pk = min(needs_feed_count - inv_w.get("WHEAT", 0), shed.get("WHEAT", 0))
                    if pk > 0: action = ["PICKUP", "WHEAT", pk]

            # --- B. Goose Livestock Care on Standing Tile ---
            if action is None and w_pos in GOOSE_COOPS and w_pos not in assigned_targets:
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
                    pref_c = get_target_crop(w_pos, day, remaining_days)
                    chosen_c = None
                    if pref_c and avail_seeds.get(pref_c, 0) > 0:
                        chosen_c = pref_c
                    elif avail_seeds.get("WHEAT", 0) > 0:
                        chosen_c = "WHEAT"
                    elif avail_seeds.get("MELON", 0) > 0:
                        chosen_c = "MELON"
                    elif avail_seeds.get("CARROT", 0) > 0:
                        chosen_c = "CARROT"
                    elif avail_seeds.get("STRAWBERRY", 0) > 0:
                        chosen_c = "STRAWBERRY"
                    if chosen_c:
                        action = ["PLANT", chosen_c]
                        avail_seeds[chosen_c] -= 1
                        assigned_targets.add(w_pos)
                elif w_pos in weeds and w_pos not in assigned_targets:
                    action = ["DIG"]
                    assigned_targets.add(w_pos)

            # --- D. Navigation ---
            if action is None:
                best_target = None
                # Day 30 Mass Harvest
                if day >= 30 or (day >= 26 and day != 28):
                    p_harv = [p for p in harvestable if p not in assigned_targets]
                    if p_harv:
                        best_target = min(p_harv, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Livestock needs (for workers in NW)
                if not best_target and assigned_quad == "NW":
                    for g_pos in GOOSE_COOPS:
                        if g_pos not in assigned_targets and g_pos not in fed_today:
                            gt = get_tile(*g_pos)
                            if isinstance(gt, dict) and gt.get("animal"):
                                if (not gt.get("fed_today", False) and (inv_w.get("WHEAT", 0) > 0 or shed.get("WHEAT", 0) > 0)) or gt.get("yield_units", 0) > 0 or gt.get("fertilizer_available", False) or not gt.get("cared_today", False):
                                    best_target = g_pos
                                    break

                # Urgent water
                if not best_target and day <= 29:
                    p0 = [p for p in urgent_water if p not in assigned_targets]
                    if p0:
                        best_target = min(p0, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Ready Harvests
                if not best_target:
                    p1_local = [p for p in harvestable if p not in assigned_targets and (("S" if p[1]>=5 else "N") + ("E" if p[0]>=5 else "W")) == assigned_quad]
                    p1_any = [p for p in harvestable if p not in assigned_targets]
                    p1 = p1_local if p1_local else p1_any
                    if p1:
                        best_target = min(p1, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Fertilization
                if not best_target and has_fert and day <= 27:
                    pf_local = [p for p in unfert_premium if p not in assigned_targets and (("S" if p[1]>=5 else "N") + ("E" if p[0]>=5 else "W")) == assigned_quad]
                    pf_any = [p for p in unfert_premium if p not in assigned_targets]
                    pf = pf_local if pf_local else pf_any
                    if pf:
                        best_target = min(pf, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Weeds
                if not best_target and weeds:
                    pw_local = [p for p in weeds if p not in assigned_targets and (("S" if p[1]>=5 else "N") + ("E" if p[0]>=5 else "W")) == assigned_quad]
                    pw_any = [p for p in weeds if p not in assigned_targets]
                    pw = pw_local if pw_local else pw_any
                    if pw:
                        best_target = min(pw, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Empty Planting
                if not best_target and (day <= 25 or day == 28) and sum(avail_seeds.values()) > 0:
                    pe_local = [p for p in empty if p not in assigned_targets and (("S" if p[1]>=5 else "N") + ("E" if p[0]>=5 else "W")) == assigned_quad]
                    pe_any = [p for p in empty if p not in assigned_targets]
                    pe = pe_local if pe_local else pe_any
                    if pe:
                        best_target = min(pe, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Routine water
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


def run_benchmark():
    print("=" * 65)
    print("BENCHMARKING OPTIMIZED STRATEGY vs 'starter'")
    print("=" * 65)
    scores = []
    for m in range(4):
        p0 = fast_agent if m % 2 == 0 else "starter"
        p1 = "starter" if m % 2 == 0 else fast_agent
        env = kaggle_environments.make("kaggriculture", configuration={"episodeSteps": 720})
        env.run([p0, p1])
        s0 = env.steps[-1][0].reward or 0
        s1 = env.steps[-1][1].reward or 0
        my_s = s0 if m % 2 == 0 else s1
        opp_s = s1 if m % 2 == 0 else s0
        scores.append(my_s)
        print(f"Match {m+1}: FastAgent = ${my_s:,.0f} | Opponent = ${opp_s:,.0f}")
    print("-" * 65)
    print(f"Average Score: ${sum(scores)/len(scores):,.0f} (Max: ${max(scores):,.0f})")
    print("=" * 65)

if __name__ == "__main__":
    run_benchmark()
