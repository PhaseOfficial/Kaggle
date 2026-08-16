"""Testing animal economics and fast multi-tile crop strategy."""

from kaggle_environments import make
from src.state import FarmState
from src.constants import CROPS, ANIMALS, PRODUCTS


def animal_test_agent(obs: dict) -> dict:
    """Agent that builds a coop, buys a goose on Day 0, and feeds/harvests daily."""
    state = FarmState(obs)
    day = state.day
    hour = state.hour
    money = state.money
    pos = state.farmer_pos

    market = []
    farmer = ["PASS"]

    # Day 0: Buy 1 Goose, 5 Wheat seeds, 5 Carrot seeds
    if state.step == 0:
        market.append(["BUY_ANIMAL", "GOOSE", 1])
        market.append(["BUY_SEED", "WHEAT", 5])
        market.append(["BUY_SEED", "CARROT", 5])

    # Always sell eggs, fertilizer, carrots in shed
    for prod in ["EGG", "FERTILIZER", "CARROT"]:
        qty = state.shed.get(prod, 0)
        if qty > 0:
            market.append(["SELL", prod, qty])

    # Keep at least 3 wheat in shed for feed, sell the rest
    wheat_qty = state.shed.get("WHEAT", 0)
    if wheat_qty > 5:
        market.append(["SELL", "WHEAT", wheat_qty - 3])

    # If shed has no wheat and step > 24, buy wheat product for animal feed if needed
    if state.shed.get("WHEAT", 0) == 0 and state.seeds.get("WHEAT", 0) == 0 and money >= 50:
        market.append(["BUY_PRODUCT", "WHEAT", 2])

    # Tile (4,3) for Coop
    coop_tile = (4, 3)
    # Tile (4,4) for Crops
    crop_tile = (4, 4)

    t_coop = state.get_tile(*coop_tile)
    t_crop = state.get_tile(*crop_tile)

    # Actions:
    # 1. If coop not built, stand on (4,3) and BUILD_COOP
    if t_coop is None:
        if pos == coop_tile:
            farmer = ["BUILD_COOP"]
        else:
            farmer = ["MOVE", "NORTH"]
        return {"farmer": farmer, "hands": [], "market": market}

    # 2. If coop built but no goose placed, PLACE GOOSE from inventory
    if isinstance(t_coop, dict) and t_coop.get("kind") == "COOP" and t_coop.get("animal") is None:
        if pos == coop_tile:
            # Must have goose in inventory or pick up from shed
            # Let's check if goose in shed
            if state.shed.get("GOOSE", 0) > 0:
                farmer = ["PICKUP", "GOOSE", 1]
            else:
                farmer = ["PLACE", "GOOSE"]
        else:
            farmer = ["MOVE", "NORTH"]
        return {"farmer": farmer, "hands": [], "market": market}

    # 3. Daily routine:
    # On coop_tile (4,3): Feed goose, care goose, collect fertilizer, harvest egg
    if isinstance(t_coop, dict) and t_coop.get("animal") == "GOOSE":
        if pos == coop_tile:
            if not t_coop.get("fed_today", False) and (state.shed.get("WHEAT", 0) > 0 or state.inventories[0].get("WHEAT", 0) > 0):
                return {"farmer": ["FEED"], "hands": [], "market": market}
            if t_coop.get("yield_units", 0) > 0:
                return {"farmer": ["HARVEST"], "hands": [], "market": market}
            if t_coop.get("fertilizer_available", False):
                return {"farmer": ["COLLECT_FERTILIZER"], "hands": [], "market": market}
            if not t_coop.get("cared_today", False):
                return {"farmer": ["CARE"], "hands": [], "market": market}

    # On crop_tile (4,4): Plant, Water, Harvest
    if pos == crop_tile:
        if isinstance(t_crop, dict) and t_crop.get("kind") == "PLANT":
            age = day - t_crop.get("planted_day", 0)
            if t_crop.get("yield_units", 0) > 0 and age >= 3:
                return {"farmer": ["HARVEST"], "hands": [], "market": market}
            if not t_crop.get("watered_today", False):
                return {"farmer": ["WATER"], "hands": [], "market": market}
        elif t_crop is None:
            if state.seeds.get("CARROT", 0) > 0:
                return {"farmer": ["PLANT", "CARROT"], "hands": [], "market": market}
            elif state.seeds.get("WHEAT", 0) > 0:
                return {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": market}
            elif money >= 20:
                market.append(["BUY_SEED", "CARROT", 2])

    # Movement between (4,3) and (4,4)
    # If coop needs attention and we are not there, move NORTH
    if isinstance(t_coop, dict) and t_coop.get("animal") == "GOOSE":
        if not t_coop.get("fed_today", False) or t_coop.get("yield_units", 0) > 0 or t_coop.get("fertilizer_available", False):
            if pos != coop_tile:
                return {"farmer": ["MOVE", "NORTH"], "hands": [], "market": market}

    # Otherwise move SOUTH to crop tile
    if pos != crop_tile:
        return {"farmer": ["MOVE", "SOUTH"], "hands": [], "market": market}

    return {"farmer": farmer, "hands": [], "market": market}


if __name__ == "__main__":
    env = make("kaggriculture", configuration={"episodeSteps": 720}, debug=True)
    env.run([animal_test_agent, "starter"])
    final = env.steps[-1]
    print(f"Animal Agent Score: ${final[0].reward:.0f} vs Starter: ${final[1].reward:.0f}")
