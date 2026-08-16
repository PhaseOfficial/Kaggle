import kaggle_environments

env = kaggle_environments.make('kaggriculture', configuration={'episodeSteps': 25}, debug=True)

def livestock_full_test_agent(obs):
    f = obs['farms'][0]
    p = obs['private']
    step = obs['step']
    farmer = tuple(f['farmer'])
    shed = p['shed']
    inv = p['inventories'][0] if p['inventories'] else {}
    tiles = f['tiles']
    
    market = []
    if step == 0:
        market.append(['BUY_ANIMAL', 'GOOSE', 1])
        market.append(['BUY_ANIMAL', 'COW', 1])
        market.append(['BUY_ANIMAL', 'SHEEP', 1])
    
    farmer_act = ['PASS']
    
    # If farmer has no animal in inv, check if animals in shed need pickup -> go to (4,4)
    has_animal_in_inv = any(inv.get(a, 0) > 0 for a in ['GOOSE', 'COW', 'SHEEP'])
    has_animal_in_shed = any(shed.get(a, 0) > 0 for a in ['GOOSE', 'COW', 'SHEEP'])
    
    if not has_animal_in_inv and has_animal_in_shed:
        if farmer != (4, 4):
            dx = 4 - farmer[0]
            dy = 4 - farmer[1]
            if dx > 0: farmer_act = ['EAST']
            elif dx < 0: farmer_act = ['WEST']
            elif dy > 0: farmer_act = ['SOUTH']
            elif dy < 0: farmer_act = ['NORTH']
        else:
            for anim in ['GOOSE', 'COW', 'SHEEP']:
                if shed.get(anim, 0) > 0:
                    farmer_act = ['PICKUP', anim, 1]
                    break
    elif has_animal_in_inv:
        for pos, (struct, anim) in [((4,3), ('COOP', 'GOOSE')), ((3,4), ('PASTURE', 'COW')), ((3,3), ('PASTURE', 'SHEEP'))]:
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
                
    return {'farmer': farmer_act, 'hands': [], 'market': market}

env.run([livestock_full_test_agent, 'pass'])
for s_idx in range(16):
    s = env.steps[s_idx][0]
    obs = s.observation
    f = obs['farms'][0]
    p = obs['private']
    inv_str = {k: v for k, v in p['inventories'][0].items() if v > 0}
    shed_str = {k: v for k, v in p['shed'].items() if v > 0}
    print(f"Step {s_idx:2d}: Farmer={f['farmer']} | Inv={inv_str} | Shed={shed_str}")
    t1 = f['tiles'][3][4]
    t2 = f['tiles'][4][3]
    t3 = f['tiles'][3][3]
    k1 = t1.get('animal') if isinstance(t1, dict) else t1
    k2 = t2.get('animal') if isinstance(t2, dict) else t2
    k3 = t3.get('animal') if isinstance(t3, dict) else t3
    print(f"         (4,3)={k1} | (3,4)={k2} | (3,3)={k3}")
