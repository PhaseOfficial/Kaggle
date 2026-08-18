import kaggle_environments
from test_opponent_counters import CounterAgent

agent = CounterAgent()
env = kaggle_environments.make("kaggriculture", configuration={"episodeSteps": 720})
env.run([agent, "starter"])
print("Step rewards:", env.steps[-1][0].reward, env.steps[-1][1].reward)
print("Steps count:", len(env.steps))
print("Final status:", env.steps[-1][0].status)
