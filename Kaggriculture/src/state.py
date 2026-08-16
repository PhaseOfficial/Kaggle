"""Farm state parser and geometric helper utilities."""

from src.constants import CROPS, LIVESTOCK_PLOTS


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
