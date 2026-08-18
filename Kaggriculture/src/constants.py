"""Kaggriculture simulation parameters, crop metrics, market tables, and livestock coordinates."""

CROPS = {
    "WHEAT": {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT": {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO": {"seed": 50, "first_yield_day": 8, "max_yield_day": 11, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 16, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON": {"seed": 80, "first_yield_day": 10, "max_yield_day": 10, "interval": 0, "max_yield": 6, "ongoing": False},
}

ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP", "first_yield_day": 4, "interval": 1, "product": "EGG"},
    "COW": {"cost": 400, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "product": "WOOL"},
}

# 12 Livestock Plots: Plot 1 (NW) + Plot 2 (NE)
LIVESTOCK_PLOTS = {
    "NW": {
        (4, 4): ("PASTURE", "COW"),     # Cow 1: Directly on (4, 4)
        (4, 3): ("PASTURE", "COW"),     # Cow 2: 1 step North (4, 3)
        (4, 2): ("PASTURE", "COW"),     # Cow 3: 2 steps North (4, 2)
        (2, 4): ("PASTURE", "COW"),     # Cow 4: 2 steps West (2, 4)
        (3, 4): ("PASTURE", "SHEEP"),   # Sheep 1: 1 step West (3, 4)
        (3, 3): ("PASTURE", "SHEEP"),   # Sheep 2: 1 step Northwest (3, 3)
    },
    "NE": {
        (5, 4): ("PASTURE", "COW"),     # Cow 5: Directly on (5, 4)
        (5, 3): ("PASTURE", "COW"),     # Cow 6: 1 step North (5, 3)
        (5, 2): ("PASTURE", "COW"),     # Cow 7: 2 steps North (5, 2)
        (7, 4): ("PASTURE", "COW"),     # Cow 8: 2 steps East (7, 4)
        (6, 4): ("PASTURE", "SHEEP"),   # Sheep 3: 1 step East (6, 4)
        (6, 3): ("PASTURE", "SHEEP"),   # Sheep 4: 1 step Northeast (6, 3)
    },
    "SW": {},
    "SE": {},
}

# Dedicated Wheat Coordinates in Plot 1 (NW) and Plot 2 (NE) to sustain 12 animals
NW_WHEAT_TILES = {(1, 4), (0, 4), (4, 1), (4, 0), (2, 3), (1, 3), (0, 3), (2, 2)}
NE_WHEAT_TILES = {(8, 4), (9, 4), (5, 1), (5, 0), (7, 3), (8, 3), (9, 3), (7, 2)}

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

SHOPS = {
    "BAKERY": ["EGG", "WHEAT"],
    "PIZZA_SHOP": ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT": ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE": ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE": ["CARROT"],
    "SMOOTHIE_SHOP": ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}

SINGLE_PRODUCT_SHOPS = {"YARN_STORE", "PET_CAFE"}
