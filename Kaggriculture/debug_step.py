import kaggle_environments
from test_opponent_counters import CounterAgent

agent = CounterAgent()
env = kaggle_environments.make("kaggriculture", configuration={"episodeSteps": 10})
env.reset()
obs0 = env.steps[0][0].observation
act0 = agent(obs0)
print(f"Step 0 Observation Player: {obs0.get('player')}")
print(f"Step 0 Action Returned: {act0}")

env.step([act0, {"farmer": ["PASS"], "hands": [], "market": []}])
obs1 = env.steps[1][0].observation
print(f"Step 1 Farm Money: {obs1['farms'][0]['money']}")
print(f"Step 1 Farm Hands: {len(obs1['farms'][0]['hands'])}")
