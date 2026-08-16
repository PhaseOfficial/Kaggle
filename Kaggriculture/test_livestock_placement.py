import kaggle_environments

env = kaggle_environments.make('kaggriculture', configuration={'episodeSteps': 50}, debug=True)

def livestock_test_agent(obs):
    f = obs['farms'][0]
    p = obs['private']
    step = obs['step']
    farmer = tuple(f['farmer'])
    shed = p['shed']
    inv = p['inventories'][0] if p['inventories'] else {}
    t_43 = f['tiles'][3][4]
    
    market = []
    if step == 0:
        market.append(['BUY_ANIMAL', 'GOOSE', 1])
        market.append(['BUY_SEED', 'WHEAT', 5])
    
    farmer_act = ['PASS']
    
    if shed.get('GOOSE', 0) > 0 and inv.get('GOOSE', 0) == 0 and farmer == (4, 4):
        farmer_act = ['PICKUP', 'GOOSE', 1]
    elif inv.get('GOOSE', 0) > 0 and farmer == (4, 4):
        farmer_act = ['NORTH']
    elif farmer == (4, 3) and t_43 is None:
        farmer_act = ['BUILD_COOP']
    elif farmer == (4, 3) and isinstance(t_43, dict) and t_43.get('kind') == 'COOP' and t_43.get('animal') is None and inv.get('GOOSE', 0) > 0:
        farmer_act = ['PLACE', 'GOOSE']
    
    return {'farmer': farmer_act, 'hands': [], 'market': market}

env.run([livestock_test_agent, 'pass'])
for s_idx in range(6):
    s = env.steps[s_idx][0]
    obs = s.observation
    f = obs['farms'][0]
    t = f['tiles'][3][4]
    farmer = f['farmer']
    shed_g = obs['private']['shed'].get('GOOSE')
    inv_g = obs['private']['inventories'][0].get('GOOSE')
    print(f"Step {s_idx}: Farmer={farmer} | Shed={shed_g} | Inv={inv_g} | Tile={t}")
