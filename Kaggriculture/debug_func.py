import kaggle_environments
from test_opponent_counters import CounterAgent

_counter_agent = CounterAgent()

def agent_func(obs):
    return _counter_agent(obs)

env = kaggle_environments.make("kaggriculture", configuration={"episodeSteps": 720})
env.run([agent_func, "starter"])
print("Step 0 reward:", env.steps[-1][0].reward, "Starter reward:", env.steps[-1][1].reward)
