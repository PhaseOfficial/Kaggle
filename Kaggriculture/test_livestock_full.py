import kaggle_environments

env = kaggle_environments.make('kaggriculture', configuration={'episodeSteps': 150}, debug=True)

LIVESTOCK_TILES = {
    (4, 3): ("COOP", "GOOSE"),
    (3, 4): ("PASTURE", "COW"),
    (3, 3): ("PASTURE", "SHEEP"),
}

def livestock_full_test_agent(obs):
    f = obs['farms'][0]
    p = obs['private']
    step = obs['step']
    day = obs['day']
    hour = obs['hour']
    farmer = tuple(f['farmer'])
    shed = p['shed']
    inv = p['inventories'][0] if p['inventories'] else {}
    tiles = f['tiles']
    money = f['money']
    
    market = []
    
    # Buy animals on Day 0
    if step == 0:
        market.append(['BUY_ANIMAL', 'GOOSE', 1])
        market.append(['BUY_ANIMAL', 'COW', 1])
        market.append(['BUY_ANIMAL', 'SHEEP', 1])
        market.append(['BUY_SEED', 'WHEAT', 15])
        market.append(['HIRE'])
        market.append(['HIRE'])
        market.append(['HIRE'])
    
    # Liquidate eggs/milk/wool/fertilizer
    for prod in ['EGG', 'MILK', 'WOOL', 'FERTILIZER']:
        if shed.get(prod, 0) > 0 and len(market) < 10:
            market.append(['SELL', prod, shed[prod]])
            
    # Workers: Farmer + hands
    # We can handle livestock actions smoothly
    farmer_act = ['PASS']
    hands_act = [['PASS']] * len(f['hands'])
    
    # Check if any animal in shed needs pickup
    if farmer == (4, 4):
        for anim in ['GOOSE', 'COW', 'SHEEP']:
            if shed.get(anim, 0) > 0 and inv.get(anim, 0) == 0:
                farmer_act = ['PICKUP', anim, 1]
                break
                
    if farmer_act == ['PASS']:
        # If farmer has an animal in inventory, navigate to its target tile
        for pos, (struct, anim) in LIVESTOCK_TILES.items():
            if inv.get(anim, 0) > 0:
                if farmer != pos:
                    dx = pos[0] - farmer[0]
                    dy = pos[1] - farmer[1]
                    if dx > 0: farmer_act = ['EAST']
                    elif dx < 0: farmer_act = ['WEST']
                    elif dy > 0: farmer_act = ['SOUTH']
                    elif dy < 0: farmer_act = ['NORTH']
                else:
                    t = tiles[pos[1]][pos[0]]
                    if t is None:
                        farmer_act = ['BUILD_COOP'] if struct == 'COOP' else ['BUILD_PASTURE']
                    elif isinstance(t, dict) and t.get('animal') is None:
                        farmer_act = ['PLACE', anim]
                break
                
    # If standing on an active animal tile:
    if farmer_act == ['PASS'] and farmer in LIVESTOCK_TILES:
        t = tiles[farmer[1]][farmer[0]]
        if isinstance(t, dict) and t.get('animal'):
            if t.get('yield_units', 0) > 0:
                farmer_act = ['HARVEST']
            elif t.get('fertilizer_available', False):
                farmer_act = ['COLLECT_FERTILIZER']
            elif not t.get('fed_today', False) and shed.get('WHEAT', 0) > 0:
                farmer_act = ['FEED']
            elif not t.get('cared_today', False):
                farmer_act = ['CARE']
                
    return {'farmer': farmer_act, 'hands': hands_act, 'market': market}

env.run([livestock_full_test_agent, 'pass'])
print("Simulation finished! Let's check animals on tiles:")
obs = env.steps[-1][0].observation
tiles = obs['farms'][0]['tiles']
for pos, (struct, anim) in LIVESTOCK_TILES.items():
    t = tiles[pos[1]][pos[0]]
    print(f"Tile {pos}: {t}")
print(f"Shed at end: {obs['private']['shed']}")
