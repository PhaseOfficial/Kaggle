"""Full-Farm Multi-Worker Zonal Agent for Kaggriculture."""

from src.state import FarmState
from src.macro_planner import ZonalMacroPlanner
from src.task_dispatcher import MultiWorkerDispatcher


def agent(obs: dict) -> dict:
    """
    Kaggriculture agent decision function.
    Returns: {"farmer": [...], "hands": [...], "market": [...]}
    """
    try:
        state = FarmState(obs)

        # 1. Macro Planner: Daily hiring, zonal seed procurement, and market liquidation
        planner = ZonalMacroPlanner(state)
        market_orders = planner.plan_market_orders()

        # 2. Multi-Worker Dispatcher: Parallel spatial task coordination for Farmer + all Hands
        dispatcher = MultiWorkerDispatcher(state)
        farmer_action, hands_actions = dispatcher.dispatch()

        return {
            "farmer": farmer_action,
            "hands": hands_actions,
            "market": market_orders,
        }
    except Exception as e:
        print(f"Agent error at step {obs.get('step')}: {e}")
        return {"farmer": ["PASS"], "hands": [], "market": []}
