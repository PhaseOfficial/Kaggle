"""Multi-worker spatial task coordinator: 6 livestock plots in NW, 100% crops on expansions."""

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
        harvestable = set(self.state.get_harvestable_tiles())
        weeds = set(self.state.get_weed_tiles())
        empty = set(self.state.get_empty_tiles())

        assigned_targets = set()
        worker_actions = []
        available_seeds = dict(self.state.seeds)

        for w_idx, w_pos in enumerate(self.workers):
            tile = self.state.get_tile(*w_pos)
            action = None

            # --- A. Farmer Special: Pickup Animal from Shed if needed ---
            if w_idx == 0:
                inv_0 = self.state.inventories[0] if self.state.inventories else {}
                has_animal_in_inv = any(inv_0.get(a, 0) > 0 for a in ["GOOSE", "COW", "SHEEP"])
                has_animal_in_shed = any(self.state.shed.get(a, 0) > 0 for a in ["GOOSE", "COW", "SHEEP"])

                if not has_animal_in_inv and has_animal_in_shed:
                    if w_pos == (4, 4):
                        for anim in ["GOOSE", "COW", "SHEEP"]:
                            if self.state.shed.get(anim, 0) > 0:
                                action = ["PICKUP", anim, 1]
                                break
                    else:
                        step = get_bfs_step(w_pos, (4, 4), self.unlocked_set)
                        action = [step] if step != "PASS" else ["PASS"]

                elif has_animal_in_inv:
                    for pos, (struct, anim) in active_livestock.items():
                        if inv_0.get(anim, 0) > 0:
                            t_target = self.state.get_tile(*pos)
                            if t_target is None or (isinstance(t_target, dict) and t_target.get("animal") is None):
                                if w_pos != pos:
                                    step = get_bfs_step(w_pos, pos, self.unlocked_set)
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
                    if not tile.get("fed_today", False) and (self.state.shed.get("WHEAT", 0) > 0 or (w_idx < len(self.state.inventories) and self.state.inventories[w_idx].get("WHEAT", 0) > 0)):
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
                            t = self.state.get_tile(*l_pos)
                            if isinstance(t, dict) and t.get("animal"):
                                if (not t.get("fed_today", False) and self.state.shed.get("WHEAT", 0) > 0) or t.get("yield_units", 0) > 0 or t.get("fertilizer_available", False):
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
                    step = get_bfs_step(w_pos, best_target, self.unlocked_set)
                    action = [step] if step != "PASS" else ["PASS"]
                else:
                    action = ["PASS"]

            worker_actions.append(action)

        farmer_action = worker_actions[0] if worker_actions else ["PASS"]
        hands_actions = worker_actions[1:] if len(worker_actions) > 1 else []

        return farmer_action, hands_actions
