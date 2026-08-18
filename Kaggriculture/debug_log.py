import kaggle_environments
from test_opponent_counters import CounterAgent
import traceback

step_log = []
class LoggingCounterAgent(CounterAgent):
    def __call__(self, obs: dict) -> dict:
        try:
            res = super().__call__(obs)
            step = obs.get("step", 0)
            if step % 50 == 0:
                money = obs.get("farms", [])[0].get("money", 0)
                step_log.append((step, money))
            return res
        except Exception as e:
            print(f"Exception at step {obs.get('step')}: {e}")
            traceback.print_exc()
            return {"farmer": ["PASS"], "hands": [], "market": []}

agent = LoggingCounterAgent()
env = kaggle_environments.make("kaggriculture", configuration={"episodeSteps": 720})
env.run([agent, "starter"])
print("Step log:", step_log)
print("Final reward:", env.steps[-1][0].reward, env.steps[-1][1].reward)
