"""Observation parsing and farm state query utilities."""

from src.constants import CROPS, ANIMALS, LAND_PRICES, LAND_ORDER


class FarmState:
    """Convenience wrapper for player farm and global game state."""

    def __init__(self, obs: dict):
        self.raw_obs = obs
        self.player_id = obs.get("player", 0)
        self.day = obs.get("day", 0)
        self.hour = obs.get("hour", 0)
        self.step = obs.get("step", self.day * 24 + self.hour)
        self.remaining_steps = max(0, 720 - self.step)
        self.remaining_days = max(0, 30 - self.day)

        farms = obs.get("farms", [])
        self.my_farm = farms[self.player_id] if self.player_id < len(farms) else {}
        self.opp_farm = farms[1 - self.player_id] if (1 - self.player_id) < len(farms) else {}

        self.money = float(self.my_farm.get("money", 0))
        self.farmer_pos = tuple(self.my_farm.get("farmer", [4, 4]))
        self.hands_pos = [tuple(h) for h in self.my_farm.get("hands", [])]
        self.tiles = self.my_farm.get("tiles", [])
        self.unlocked_quadrants = set(self.my_farm.get("unlocked_quadrants", ["NW"]))
        self.hires_today = self.my_farm.get("hires_today", 0)

        private = obs.get("private", {}) or {}
        self.shed = private.get("shed", {}) or {}
        self.seeds = private.get("seeds", {}) or {}
        self.inventories = private.get("inventories", [])

        market = obs.get("market", {}) or {}
        self.market_inv = market.get("inventory", {}) or {}
        self.market_prices = market.get("prices", {}) or {}

        town = obs.get("town", {}) or {}
        self.unlocked_shops = town.get("unlocked_shops", []) or []

        self.board_size = len(self.tiles) if self.tiles else 10

    def is_tile_unlocked(self, x: int, y: int) -> bool:
        """Checks if (x, y) belongs to an unlocked quadrant."""
        if x < 0 or x >= self.board_size or y < 0 or y >= self.board_size:
            return False
        quad_x = "W" if x < self.board_size // 2 else "E"
        quad_y = "N" if y < self.board_size // 2 else "S"
        quad = quad_y + quad_x
        return quad in self.unlocked_quadrants

    def get_tile(self, x: int, y: int):
        """Returns tile content at (x, y)."""
        if 0 <= y < len(self.tiles) and 0 <= x < len(self.tiles[y]):
            return self.tiles[y][x]
        return "LOCKED"

    def get_all_unlocked_coords(self) -> list[tuple[int, int]]:
        """Returns all unlocked grid coordinates."""
        coords = []
        for y in range(self.board_size):
            for x in range(self.board_size):
                if self.is_tile_unlocked(x, y):
                    coords.append((x, y))
        return coords

    def get_empty_tiles(self) -> list[tuple[int, int]]:
        """Returns all empty, unlocked tiles."""
        return [(x, y) for (x, y) in self.get_all_unlocked_coords() if self.get_tile(x, y) is None]

    def get_weed_tiles(self) -> list[tuple[int, int]]:
        """Returns all tiles containing weeds."""
        weeds = []
        for x, y in self.get_all_unlocked_coords():
            t = self.get_tile(x, y)
            if isinstance(t, dict) and t.get("kind") == "WEED":
                weeds.append((x, y))
        return weeds

    def get_urgent_water_tiles(self) -> list[tuple[int, int]]:
        """Returns crops that are about to turn into weeds (missed 1 water day and unwatered today)."""
        urgent = []
        for x, y in self.get_all_unlocked_coords():
            t = self.get_tile(x, y)
            if isinstance(t, dict) and t.get("kind") == "PLANT":
                if not t.get("watered_today", False) and t.get("consecutive_unwatered", 0) >= 1:
                    urgent.append((x, y))
        return urgent

    def get_routine_water_tiles(self) -> list[tuple[int, int]]:
        """Returns crops that need daily watering today."""
        water_needed = []
        for x, y in self.get_all_unlocked_coords():
            t = self.get_tile(x, y)
            if isinstance(t, dict) and t.get("kind") == "PLANT":
                if not t.get("watered_today", False):
                    water_needed.append((x, y))
        return water_needed

    def get_harvestable_tiles(self) -> list[tuple[int, int]]:
        """Returns plant or animal tiles ready for harvest."""
        ready = []
        for x, y in self.get_all_unlocked_coords():
            t = self.get_tile(x, y)
            if not isinstance(t, dict):
                continue
            kind = t.get("kind")
            if kind == "PLANT":
                crop = t.get("crop")
                crop_info = CROPS.get(crop, {})
                age = self.day - t.get("planted_day", 0)
                ongoing = crop_info.get("ongoing", False)
                max_yield_day = crop_info.get("max_yield_day", 4)
                yield_units = t.get("yield_units", 0)

                if ongoing:
                    if yield_units > 0:
                        ready.append((x, y))
                else:
                    # One-time crop: harvest when yield units available or reached max yield day
                    if yield_units > 0 and (age >= max_yield_day or self.remaining_days <= 1):
                        ready.append((x, y))
            elif kind in ("COOP", "PASTURE"):
                if t.get("yield_units", 0) > 0:
                    ready.append((x, y))
        return ready

    def get_unfed_animals(self) -> list[tuple[int, int]]:
        """Returns animal structures where the animal is unfed today."""
        unfed = []
        for x, y in self.get_all_unlocked_coords():
            t = self.get_tile(x, y)
            if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE"):
                if t.get("animal") and not t.get("fed_today", False):
                    unfed.append((x, y))
        return unfed

    def get_total_shed_non_seed_count(self) -> int:
        """Returns total non-seed items in shed (subject to shedCapacity=100)."""
        return sum(self.shed.values())

    def get_next_land_price(self) -> tuple[str, int] | None:
        """Returns next land quadrant to buy and its price, or None if fully expanded."""
        for i, quad in enumerate(LAND_ORDER):
            if quad not in self.unlocked_quadrants:
                return quad, LAND_PRICES[i]
        return None
