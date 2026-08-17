import kaggle_environments
from test_strategy_v8 import agent_v8

def trace(agent_func, name):
    print("=" * 60)
    print(f"TRACING: {name}")
    print("=" * 60)
    env = kaggle_environments.make("kaggriculture", configuration={"episodeSteps": 720}, debug=True)
    env.run([agent_func, "starter"])
    for day in range(31):
        step_idx = min(day * 24, len(env.steps) - 1)
        s = env.steps[step_idx][0]
        obs = s.observation
        f = obs["farms"][0]
        p = obs["private"]
        shed_str = {k: v for k, v in p["shed"].items() if v > 0}
        seeds_str = {k: v for k, v in p["seeds"].items() if v > 0}
        tiles = f["tiles"]
        plant_count = sum(1 for row in tiles for t in row if isinstance(t, dict) and t.get("kind") == "PLANT")
        weed_count = sum(1 for row in tiles for t in row if isinstance(t, dict) and t.get("kind") == "WEED")
        animal_count = sum(1 for row in tiles for t in row if isinstance(t, dict) and t.get("animal"))
        print(f"Day {day:2d} (Step {step_idx:3d}): Money=${f['money']:7,.0f} | Plants={plant_count:2d} | Animals={animal_count:2d} | Weeds={weed_count:2d} | Quads={len(f['unlocked_quadrants'])} | Seeds={seeds_str} | Shed={shed_str}")

if __name__ == "__main__":
    trace(agent_v8, "AgentV8")
