"""
Opponent Counter Validation Suite with Function Wrappers.
Simulates matches against 3 distinct opponent archetypes:
1. MonoMelonRusher: Floods 20+ Melons on Day 0-12
2. LivestockSpecialist: Expands pastures and cows/sheep
3. StarterAgent: Default baseline
"""

import math
from collections import Counter, deque
import kaggle_environments
from src.opponent_tracker import OpponentTracker
from src.game_theoretic_optimizer import CournotNashOptimizer

CROPS = {
    "WHEAT": {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT": {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO": {"seed": 50, "first_yield_day": 8, "max_yield_day": 11, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 16, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON": {"seed": 80, "first_yield_day": 10, "max_yield_day": 10, "interval": 0, "max_yield": 6, "ongoing": False},
}

LIVESTOCK_PLOTS = {
    (4, 4): ("PASTURE", "COW"),
    (4, 3): ("PASTURE", "COW"),
    (4, 2): ("PASTURE", "COW"),
    (2, 4): ("PASTURE", "COW"),
    (3, 4): ("PASTURE", "SHEEP"),
    (3, 3): ("PASTURE", "SHEEP"),
}

NW_WHEAT_TILES = {(1, 4), (0, 4), (4, 1), (4, 0), (2, 3), (1, 3), (0, 3), (2, 2)}
PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]
FIBONACCI_COSTS = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377]


def get_hire_cost(n: int) -> int:
    if n < len(FIBONACCI_COSTS): return FIBONACCI_COSTS[n]
    a, b = FIBONACCI_COSTS[-2], FIBONACCI_COSTS[-1]
    for _ in range(n - len(FIBONACCI_COSTS) + 1):
        a, b = b, a + b
    return b


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
        return [(x, y) for (x, y) in self.get_all_unlocked_coords() if self.get_tile(x, y) is None and (x, y) not in LIVESTOCK_PLOTS]

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
                    c_info = CROPS.get(crop, {})
                    age = self.day - t.get("planted_day", 0)
                    ongoing = c_info.get("ongoing", False)
                    max_y_day = c_info.get("max_yield_day", 4)
                    if t.get("yield_units", 0) > 0:
                        if self.day >= 26 or ongoing or age >= max_y_day or self.remaining_days <= 1:
                            ready.append((x, y))
                elif t.get("kind") in ("COOP", "PASTURE"):
                    if t.get("yield_units", 0) > 0:
                        ready.append((x, y))
        return ready


def get_bfs_step(start: tuple[int, int], target: tuple[int, int], unlocked_tiles: set[tuple[int, int]]) -> str:
    if start == target or target not in unlocked_tiles: return "PASS"
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


# =====================================================================
# OPPONENT BOTS FOR TESTING
# =====================================================================
def mono_melon_rusher_bot(obs: dict) -> dict:
    orders = []
    player_id = obs.get("player", 1)
    farms = obs.get("farms", [])
    my_farm = farms[player_id] if player_id < len(farms) else {}
    money = my_farm.get("money", 0)
    day = obs.get("day", 0)
    seeds = obs.get("private", {}).get("seeds", {})
    shed = obs.get("private", {}).get("shed", {})
    hires = my_farm.get("hires_today", 0)

    if hires < 4 and money >= 20:
        orders.append(["HIRE"])
    if day <= 2 and seeds.get("MELON", 0) < 15 and money >= 80:
        orders.append(["BUY_SEED", "MELON", min(15, int(money // 80))])
    if shed.get("MELON", 0) > 0:
        orders.append(["SELL", "MELON", shed.get("MELON", 0)])

    farmer_pos = tuple(my_farm.get("farmer", [4, 4]))
    farmer_act = ["PASS"]
    tiles = my_farm.get("tiles", [])
    if 0 <= farmer_pos[1] < len(tiles) and 0 <= farmer_pos[0] < len(tiles[0]):
        tile = tiles[farmer_pos[1]][farmer_pos[0]]
        if tile is None and seeds.get("MELON", 0) > 0:
            farmer_act = ["PLANT", "MELON"]
        elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
            if tile.get("yield_units", 0) > 0: farmer_act = ["HARVEST"]
            elif not tile.get("watered_today", False): farmer_act = ["WATER"]

    return {"farmer": farmer_act, "hands": [["PASS"]] * len(my_farm.get("hands", [])), "market": orders}


def create_counter_agent_func():
    tracker = None
    optimizer = None

    def agent_func(obs: dict) -> dict:
        nonlocal tracker, optimizer
        state = FarmState(obs)
        opp_id = 1 - state.player_id
        if tracker is None or tracker.opp_id != opp_id:
            tracker = OpponentTracker(opp_id)
            optimizer = CournotNashOptimizer(tracker)

        tracker.update(obs)
        orders = []
        max_orders = 10
        money = state.money
        day = state.day
        step = state.step
        rem_days = state.remaining_days
        num_quads = len(state.unlocked_quadrants)

        # 1. FIBONACCI HIRING
        base_hires = 5 if num_quads == 1 else (7 if num_quads == 2 else 9)
        harv_count = len(state.get_harvestable_tiles())
        if harv_count >= 15 and money >= 1000: base_hires = min(base_hires + 1, 10)
        if harv_count >= 25 and money >= 3000: base_hires = min(base_hires + 1, 11)
        if day <= 3: base_hires = min(base_hires, 5)
        elif money < 300: base_hires = min(base_hires, 5)

        current_hires = state.hires_today
        while current_hires < base_hires and len(orders) < max_orders:
            cost = get_hire_cost(current_hires)
            reserve = 200 if day < 26 else 0
            if money >= cost and (money - cost) >= reserve:
                orders.append(["HIRE"])
                money -= cost
                current_hires += 1
            else:
                break

        # 2. LIVESTOCK PROCUREMENT (4 Cows + 2 Sheep)
        target_cows = 4
        target_sheep = 2
        total_cows = sum(1 for p, info in LIVESTOCK_PLOTS.items() if info[1] == "COW" and isinstance(state.get_tile(*p), dict) and state.get_tile(*p).get("animal") == "COW") + state.shed.get("COW", 0) + sum(inv.get("COW", 0) for inv in state.inventories)
        total_sheep = sum(1 for p, info in LIVESTOCK_PLOTS.items() if info[1] == "SHEEP" and isinstance(state.get_tile(*p), dict) and state.get_tile(*p).get("animal") == "SHEEP") + state.shed.get("SHEEP", 0) + sum(inv.get("SHEEP", 0) for inv in state.inventories)

        if (day >= 1 or state.shed.get("WHEAT", 0) >= 2) and day <= 20 and len(orders) < max_orders:
            while total_cows < target_cows and money >= 500 and len(orders) < max_orders:
                orders.append(["BUY_ANIMAL", "COW", 1])
                money -= 400
                total_cows += 1
            while total_sheep < target_sheep and money >= 600 and len(orders) < max_orders:
                orders.append(["BUY_ANIMAL", "SHEEP", 1])
                money -= 500
                total_sheep += 1

        all_plot1_stocked = (total_cows >= target_cows and total_sheep >= target_sheep)

        # 3. CONTROLLED LAND EXPANSION
        if day <= 20 and len(orders) < max_orders and all_plot1_stocked:
            if "NE" not in state.unlocked_quadrants and money >= 2500 and day <= 10:
                orders.append(["BUY_LAND", "NE"])
                money -= 1000
                num_quads += 1
            elif "SW" not in state.unlocked_quadrants and money >= 5000 and day <= 15:
                orders.append(["BUY_LAND", "SW"])
                money -= 2000
                num_quads += 1

        # 4. GAME-THEORETIC SEED PURCHASING
        empty_tiles = state.get_empty_tiles()
        weed_tiles = state.get_weed_tiles()
        needed_counts = Counter()

        if day in (27, 28):
            total_empty = len(empty_tiles) + len(weed_tiles)
            needed_counts["WHEAT"] = max(needed_counts["WHEAT"], total_empty + 10)
        else:
            for pos in empty_tiles + weed_tiles:
                quad = state.get_quadrant_for_pos(*pos)
                c = optimizer.select_best_response_crop(pos, quad, day, rem_days, state.market_inv, NW_WHEAT_TILES)
                if c: needed_counts[c] += 1

        wheat_buffer = max(0, 12 - state.seeds.get("WHEAT", 0))
        if wheat_buffer > 0: needed_counts["WHEAT"] += wheat_buffer

        spendable = max(0, money - 200) if day < 26 else money
        for crop in ["WHEAT", "MELON", "STRAWBERRY", "TOMATO", "CARROT"]:
            if len(orders) >= max_orders: break
            count = needed_counts.get(crop, 0)
            if count <= 0: continue
            held = state.seeds.get(crop, 0)
            buy_needed = max(0, count - held)
            if buy_needed > 0:
                seed_cost = CROPS[crop]["seed"]
                affordable = min(buy_needed, int(spendable // seed_cost)) if seed_cost > 0 else 0
                if affordable > 0:
                    batch = min(affordable, 25)
                    orders.append(["BUY_SEED", crop, batch])
                    spendable -= seed_cost * batch

        # 5. MARKET FRONT-RUNNING & LIQUIDATION
        for product in PRODUCTS:
            if len(orders) >= max_orders: break
            qty = state.shed.get(product, 0)
            if qty <= 0: continue

            if product == "WHEAT" and day < 29:
                if qty > 10: orders.append(["SELL", "WHEAT", min(qty - 10, 20)])
                continue
            if product == "FERTILIZER" and day < 28:
                if qty > 4: orders.append(["SELL", "FERTILIZER", qty - 4])
                continue
            if day >= 29 or rem_days <= 2:
                orders.append(["SELL", product, qty])
                continue

            safe_qty = optimizer.compute_safe_liquidation(product, qty, state.market_inv, day, step, rem_days)
            if safe_qty > 0:
                orders.append(["SELL", product, safe_qty])

        # Worker tasks
        workers = [state.farmer_pos] + state.hands_pos
        unlocked_set = set(state.get_all_unlocked_coords())
        active_livestock = dict(LIVESTOCK_PLOTS)

        urgent_water = set(state.get_urgent_water_tiles())
        routine_water = set(state.get_routine_water_tiles())
        unfert_premium = set(state.get_unfertilized_premium_tiles())
        harvestable = set(state.get_harvestable_tiles())
        weeds = set(state.get_weed_tiles())
        empty = set(state.get_empty_tiles())

        active_quads_list = sorted(list(state.unlocked_quadrants))
        worker_quad_map = {}
        for w_idx in range(len(workers)):
            if w_idx == 0: worker_quad_map[w_idx] = "NW"
            else: worker_quad_map[w_idx] = active_quads_list[(w_idx - 1) % len(active_quads_list)]

        assigned_targets = set()
        fed_animals_today = set()
        fertilized_today = set()
        worker_actions = []
        available_seeds = dict(state.seeds)
        placement_order = [(4, 4), (4, 3), (4, 2), (2, 4), (3, 4), (3, 3)]

        for w_idx, w_pos in enumerate(workers):
            tile = state.get_tile(*w_pos)
            action = None
            assigned_quad = worker_quad_map.get(w_idx, "NW")
            inv_w = state.inventories[w_idx] if w_idx < len(state.inventories) else {}
            has_fert = inv_w.get("FERTILIZER", 0) > 0

            # --- A. Farmer Special: Setup animals & Feed Pickup ---
            if w_idx == 0 and day <= 28:
                has_animal_in_inv = any(inv_w.get(a, 0) > 0 for a in ["COW", "SHEEP"])
                has_animal_in_shed = any(state.shed.get(a, 0) > 0 for a in ["COW", "SHEEP"])
                needs_feed_count = sum(1 for p in active_livestock if isinstance(state.get_tile(*p), dict) and state.get_tile(*p).get("animal") and not state.get_tile(*p).get("fed_today", False))

                if not has_animal_in_inv and has_animal_in_shed:
                    if w_pos == (4, 4):
                        for anim in ["COW", "SHEEP"]:
                            if state.shed.get(anim, 0) > 0:
                                action = ["PICKUP", anim, 1]
                                break
                    else:
                        step_dir = get_bfs_step(w_pos, (4, 4), unlocked_set)
                        action = [step_dir] if step_dir != "PASS" else ["PASS"]

                elif has_animal_in_inv:
                    for pos in placement_order:
                        if pos in active_livestock:
                            struct, anim = active_livestock[pos]
                            if inv_w.get(anim, 0) > 0:
                                t_target = state.get_tile(*pos)
                                if t_target is None or (isinstance(t_target, dict) and t_target.get("animal") is None):
                                    if w_pos != pos:
                                        step_dir = get_bfs_step(w_pos, pos, unlocked_set)
                                        action = [step_dir] if step_dir != "PASS" else ["PASS"]
                                    else:
                                        if tile is None:
                                            action = ["BUILD_PASTURE"]
                                        elif isinstance(tile, dict) and tile.get("animal") is None:
                                            action = ["PLACE", anim]
                                    break

                elif w_pos == (4, 4) and needs_feed_count > 0 and inv_w.get("WHEAT", 0) < needs_feed_count and state.shed.get("WHEAT", 0) > 0:
                    pk = min(needs_feed_count - inv_w.get("WHEAT", 0), state.shed.get("WHEAT", 0))
                    if pk > 0: action = ["PICKUP", "WHEAT", pk]

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
                elif day <= 28 and has_fert and w_pos in unfert_premium and w_pos not in fertilized_today:
                    action = ["FERTILIZE"]
                    fertilized_today.add(w_pos)
                    assigned_targets.add(w_pos)
                elif day <= 29 and w_pos in routine_water and w_pos not in assigned_targets:
                    action = ["WATER"]
                    assigned_targets.add(w_pos)
                elif w_pos in empty and (day <= 25 or day == 28) and w_pos not in assigned_targets:
                    quad = state.get_quadrant_for_pos(*w_pos)
                    pref_c = optimizer.select_best_response_crop(w_pos, quad, day, rem_days, state.market_inv, NW_WHEAT_TILES)
                    chosen_c = None
                    if pref_c and available_seeds.get(pref_c, 0) > 0: chosen_c = pref_c
                    elif available_seeds.get("WHEAT", 0) > 0: chosen_c = "WHEAT"
                    elif available_seeds.get("STRAWBERRY", 0) > 0: chosen_c = "STRAWBERRY"
                    elif available_seeds.get("MELON", 0) > 0: chosen_c = "MELON"
                    if chosen_c:
                        action = ["PLANT", chosen_c]
                        available_seeds[chosen_c] -= 1
                        assigned_targets.add(w_pos)
                elif w_pos in weeds and w_pos not in assigned_targets:
                    action = ["DIG"]
                    assigned_targets.add(w_pos)

            # --- D. BFS Navigation ---
            if action is None:
                best_target = None
                if day >= 30 or (day >= 26 and day != 28):
                    p_harv_local = [p for p in harvestable if p not in assigned_targets and state.get_quadrant_for_pos(*p) == assigned_quad]
                    p_harv_any = [p for p in harvestable if p not in assigned_targets]
                    p_harv = p_harv_local if p_harv_local else p_harv_any
                    if p_harv:
                        best_target = min(p_harv, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and w_idx == 0:
                    for l_pos in placement_order:
                        if l_pos in active_livestock and l_pos not in assigned_targets and l_pos not in fed_animals_today:
                            t = state.get_tile(*l_pos)
                            if isinstance(t, dict) and t.get("animal"):
                                if (not t.get("fed_today", False) and state.shed.get("WHEAT", 0) > 0) or t.get("yield_units", 0) > 0 or t.get("fertilizer_available", False):
                                    best_target = l_pos
                                    break

                if not best_target and day <= 29:
                    p0 = [p for p in urgent_water if p not in assigned_targets]
                    if p0: best_target = min(p0, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target:
                    p1_local = [p for p in harvestable if p not in assigned_targets and state.get_quadrant_for_pos(*p) == assigned_quad]
                    p1_any = [p for p in harvestable if p not in assigned_targets]
                    p1 = p1_local if p1_local else p1_any
                    if p1: best_target = min(p1, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and has_fert and day <= 27:
                    pf_local = [p for p in unfert_premium if p not in assigned_targets and p not in fertilized_today and state.get_quadrant_for_pos(*p) == assigned_quad]
                    pf_any = [p for p in unfert_premium if p not in assigned_targets and p not in fertilized_today]
                    pf = pf_local if pf_local else pf_any
                    if pf: best_target = min(pf, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and weeds:
                    pw_local = [p for p in weeds if p not in assigned_targets and state.get_quadrant_for_pos(*p) == assigned_quad]
                    pw_any = [p for p in weeds if p not in assigned_targets]
                    pw = pw_local if pw_local else pw_any
                    if pw: best_target = min(pw, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and (day <= 25 or day == 28) and sum(available_seeds.values()) > 0:
                    pe_local = [p for p in empty if p not in assigned_targets and state.get_quadrant_for_pos(*p) == assigned_quad]
                    pe_any = [p for p in empty if p not in assigned_targets]
                    pe = pe_local if pe_local else pe_any
                    if pe: best_target = min(pe, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if not best_target and day <= 29:
                    pr_local = [p for p in routine_water if p not in assigned_targets and state.get_quadrant_for_pos(*p) == assigned_quad]
                    pr_any = [p for p in routine_water if p not in assigned_targets]
                    pr = pr_local if pr_local else pr_any
                    if pr: best_target = min(pr, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                if best_target and best_target != w_pos:
                    assigned_targets.add(best_target)
                    step_dir = get_bfs_step(w_pos, best_target, unlocked_set)
                    action = [step_dir] if step_dir != "PASS" else ["PASS"]
                else:
                    action = ["PASS"]

            worker_actions.append(action)

        farmer_action = worker_actions[0] if worker_actions else ["PASS"]
        hands_actions = worker_actions[1:] if len(worker_actions) > 1 else []
        return {"farmer": farmer_action, "hands": hands_actions, "market": orders[:max_orders]}

    return agent_func


if __name__ == "__main__":
    print("\n=======================================================")
    print("RUNNING OPPONENT COUNTER TOURNAMENT")
    print("=======================================================")

    # Match 1: vs Starter
    agent_match1 = create_counter_agent_func()
    env1 = kaggle_environments.make("kaggriculture", configuration={"episodeSteps": 720})
    env1.run([agent_match1, "starter"])
    score_p0 = env1.steps[-1][0].reward
    score_p1 = env1.steps[-1][1].reward
    print(f"MATCH 1 vs Starter: MyAgent=${score_p0:,.2f} | Starter=${score_p1:,.2f}")

    # Match 2: vs Mono-Melon Rusher
    agent_match2 = create_counter_agent_func()
    env2 = kaggle_environments.make("kaggriculture", configuration={"episodeSteps": 720})
    env2.run([agent_match2, mono_melon_rusher_bot])
    score_p0_2 = env2.steps[-1][0].reward
    score_p1_2 = env2.steps[-1][1].reward
    print(f"MATCH 2 vs MonoMelonRusher: MyAgent=${score_p0_2:,.2f} | Rusher=${score_p1_2:,.2f}")
    print("=======================================================\n")
