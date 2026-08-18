"""
Opponent Tracker and Machine Learning Supply Forecaster for Kaggriculture.
Analyzes opponent farm state, tracks crop maturity timelines, predicts market dumps,
and classifies opponent strategy archetypes.
"""

from collections import Counter, defaultdict

CROPS_INFO = {
    "WHEAT": {"first_yield_day": 2, "max_yield_day": 4, "max_yield": 6, "ongoing": False},
    "CARROT": {"first_yield_day": 2, "max_yield_day": 3, "max_yield": 4, "ongoing": False},
    "TOMATO": {"first_yield_day": 8, "max_yield_day": 11, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"first_yield_day": 10, "max_yield_day": 16, "max_yield": 4, "ongoing": True},
    "MELON": {"first_yield_day": 10, "max_yield_day": 10, "max_yield": 6, "ongoing": False},
}


class OpponentTracker:
    def __init__(self, opponent_id: int):
        self.opp_id = opponent_id
        self.history = []
        self.archetype = "PASSIVE_STARTER"

    def update(self, obs: dict) -> dict:
        farms = obs.get("farms", [])
        if self.opp_id >= len(farms):
            return self._default_state()

        opp_farm = farms[self.opp_id]
        money = opp_farm.get("money", 0)
        unlocked = opp_farm.get("unlocked_quadrants", ["NW"])
        tiles = opp_farm.get("tiles", [])
        hires = opp_farm.get("hires_today", 0)
        day = obs.get("day", 0)

        # 1. Feature Extraction
        crop_counts = Counter()
        animal_counts = Counter()
        forecast_dumps = defaultdict(lambda: defaultdict(int))
        total_plants = 0
        total_animals = 0

        for r_idx, row in enumerate(tiles):
            for c_idx, tile in enumerate(row):
                if isinstance(tile, dict):
                    kind = tile.get("kind")
                    if kind == "PLANT":
                        crop = tile.get("crop")
                        crop_counts[crop] += 1
                        total_plants += 1

                        planted_day = tile.get("planted_day", 0)
                        c_info = CROPS_INFO.get(crop, {"max_yield_day": 4, "max_yield": 4})
                        max_y_day = c_info.get("max_yield_day", 4)
                        exp_day = planted_day + max_y_day
                        exp_yield = max(1, tile.get("yield_units", 2))
                        forecast_dumps[crop][exp_day] += exp_yield

                    elif kind in ("COOP", "PASTURE"):
                        animal = tile.get("animal")
                        if animal:
                            animal_counts[animal] += 1
                            total_animals += 1
                            prod = "MILK" if animal == "COW" else ("WOOL" if animal == "SHEEP" else "EGG")
                            for d in range(day, min(31, day + 10)):
                                forecast_dumps[prod][d] += 1

        # 2. Archetype Classification
        if crop_counts.get("MELON", 0) >= 8 or (total_plants > 0 and crop_counts.get("MELON", 0) / total_plants >= 0.45):
            self.archetype = "MONO_MELON"
        elif crop_counts.get("TOMATO", 0) >= 8 or (total_plants > 0 and crop_counts.get("TOMATO", 0) / total_plants >= 0.45):
            self.archetype = "TOMATO_RUSH"
        elif total_animals >= 3 or animal_counts.get("COW", 0) >= 2:
            self.archetype = "LIVESTOCK_HEAVY"
        elif len(unlocked) >= 2 and total_plants >= 15 and len(crop_counts) >= 3:
            self.archetype = "DIVERSIFIED"
        else:
            self.archetype = "PASSIVE_STARTER"

        state_summary = {
            "money": money,
            "unlocked": unlocked,
            "crop_counts": dict(crop_counts),
            "animal_counts": dict(animal_counts),
            "total_plants": total_plants,
            "total_animals": total_animals,
            "archetype": self.archetype,
            "forecast_dumps": {k: dict(v) for k, v in forecast_dumps.items()},
        }
        self.history.append(state_summary)
        return state_summary

    def get_projected_supply_in_window(self, product: str, start_day: int, end_day: int) -> int:
        if not self.history:
            return 0
        latest = self.history[-1]
        dumps = latest.get("forecast_dumps", {}).get(product, {})
        total = 0
        for d in range(start_day, end_day + 1):
            total += dumps.get(d, 0)
        return total

    def _default_state(self) -> dict:
        return {
            "money": 0,
            "unlocked": ["NW"],
            "crop_counts": {},
            "animal_counts": {},
            "total_plants": 0,
            "total_animals": 0,
            "archetype": "PASSIVE_STARTER",
            "forecast_dumps": {},
        }
