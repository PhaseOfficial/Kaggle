"""Multi-worker spatial task coordinator: Strictly Wheat, Melon, and Strawberry after Melon."""

from collections import deque
from src.constants import CROPS, LIVESTOCK_PLOTS
from src.state import FarmState
from src.macro_planner import get_target_crop_for_pos


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
                if dx == 1:
                    return "EAST"
                if dx == -1:
                    return "WEST"
                if dy == 1:
                    return "SOUTH"
                if dy == -1:
                    return "NORTH"
            return "PASS"

        for dx, dy in [(0, -1), (0, 1), (1, 0), (-1, 0)]:
            nxt = (curr[0] + dx, curr[1] + dy)
            if nxt in unlocked_tiles and nxt not in visited:
                visited.add(nxt)
                queue.append(path + [nxt])

    return "PASS"


class MultiWorkerDispatcher:
    def __init__(self, state: FarmState):
        self.state = state
        self.workers = [self.state.farmer_pos] + self.state.hands_pos
        self.unlocked_set = set(self.state.get_all_unlocked_coords())

    def dispatch(self) -> tuple[list, list]:
        day = self.state.day
        rem_days = self.state.remaining_days

        # Active livestock exclusively in NW
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

        for w_idx, w_pos in enumerate(workers):
            tile = self.state.get_tile(*w_pos)
            action = None
            assigned_quad = worker_quad_map.get(w_idx, "NW")
            inv_w = self.state.inventories[w_idx] if w_idx < len(self.state.inventories) else {}
            has_fert = inv_w.get("FERTILIZER", 0) > 0

            # --- A. Farmer Special: Pickup Animal / Fertilizer from Shed ---
            if w_idx == 0 and day <= 24:
                has_animal_in_inv = any(inv_w.get(a, 0) > 0 for a in ["COW", "SHEEP"])
                has_animal_in_shed = any(self.state.shed.get(a, 0) > 0 for a in ["COW", "SHEEP"])

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

            # --- B. Livestock Care on Standing Plot ---
            if action is None and w_pos in active_livestock and w_pos not in assigned_targets:
                req_struct, req_animal = active_livestock[w_pos]
                if isinstance(tile, dict) and tile.get("animal"):
                    if not tile.get("fed_today", False) and w_pos not in fed_animals_today and (self.state.shed.get("WHEAT", 0) > 0 or inv_w.get("WHEAT", 0) > 0):
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

            # --- C. Crop Standing Actions (Harvest -> Urgent Water -> Fertilize -> Plant -> Routine Water -> Dig) ---
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

                # On Day 30, MASS HARVEST IS ABSOLUTE TOP PRIORITY FOR ALL 13 WORKERS!
                if day >= 30 or (day >= 26 and day != 28):
                    p_harv_local = [p for p in harvestable if p not in assigned_targets and self.state.get_quadrant_for_pos(*p) == assigned_quad]
                    p_harv_any = [p for p in harvestable if p not in assigned_targets]
                    p_harv = p_harv_local if p_harv_local else p_harv_any
                    if p_harv:
                        best_target = min(p_harv, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 0: Livestock needs (Right next to Shed!)
                if not best_target and w_idx == 0:
                    for l_pos in active_livestock:
                        if l_pos not in assigned_targets and l_pos not in fed_animals_today:
                            t = self.state.get_tile(*l_pos)
                            if isinstance(t, dict) and t.get("animal"):
                                if (not t.get("fed_today", False) and self.state.shed.get("WHEAT", 0) > 0) or t.get("yield_units", 0) > 0 or t.get("fertilizer_available", False):
                                    best_target = l_pos
                                    break

                # Priority 1: Urgent water (prevent withering)
                if not best_target and day <= 29:
                    p0 = [p for p in urgent_water if p not in assigned_targets]
                    if p0:
                        best_target = min(p0, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 2: Ready harvests
                if not best_target:
                    p1_local = [p for p in harvestable if p not in assigned_targets and self.state.get_quadrant_for_pos(*p) == assigned_quad]
                    p1_any = [p for p in harvestable if p not in assigned_targets]
                    p1 = p1_local if p1_local else p1_any
                    if p1:
                        best_target = min(p1, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 3: Targeted Fertilization of Premium Crops if carrying fertilizer
                if not best_target and has_fert and day <= 27:
                    p_fert_local = [p for p in unfertilized_premium if p not in assigned_targets and p not in fertilized_today and self.state.get_quadrant_for_pos(*p) == assigned_quad]
                    p_fert_any = [p for p in unfertilized_premium if p not in assigned_targets and p not in fertilized_today]
                    p_fert = p_fert_local if p_fert_local else p_fert_any
                    if p_fert:
                        best_target = min(p_fert, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 4: CLEAR WEEDS in assigned quadrant
                if not best_target and weeds:
                    p_weed_local = [p for p in weeds if p not in assigned_targets and self.state.get_quadrant_for_pos(*p) == assigned_quad]
                    p_weed_any = [p for p in weeds if p not in assigned_targets]
                    p_weed = p_weed_local if p_weed_local else p_weed_any
                    if p_weed:
                        best_target = min(p_weed, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 5: EMPTY TILES in assigned quadrant (Plant 100% of farm on Day 28 Wheat Blitz!)
                if not best_target and (day <= 25 or day == 28) and sum(available_seeds.values()) > 0:
                    p3_local = [p for p in empty if p not in assigned_targets and self.state.get_quadrant_for_pos(*p) == assigned_quad]
                    p3_any = [p for p in empty if p not in assigned_targets]
                    p3 = p3_local if p3_local else p3_any
                    if p3:
                        best_target = min(p3, key=lambda p: abs(p[0] - w_pos[0]) + abs(p[1] - w_pos[1]))

                # Priority 6: Routine daily water
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
