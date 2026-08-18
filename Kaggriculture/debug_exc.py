import kaggle_environments
from test_opponent_counters import CounterAgent
import traceback

class LoggingCounterAgent(CounterAgent):
    def __call__(self, obs: dict) -> dict:
        try:
            return super().__call__(obs)
        except Exception as e:
            print(f"Exception at step {obs.get('step')}: {e}")
            traceback.print_exc()
            return {"farmer": ["PASS"], "hands": [], "market": []}

agent = LoggingCounterAgent()
env = kaggle_environments.make("kaggriculture", configuration={"episodeSteps": 10})
env.run([agent, "starter"])
