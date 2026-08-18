"""
Diagnostic breakdown of agent performance: revenues, expenses, harvests, waste.
"""

import kaggle_environments
import optimize_100k

def run_diagnostic():
    env = kaggle_environments.make("kaggriculture", configuration={"episodeSteps": 720})
    env.run([optimize_100k.agent_100k, "starter"])
    
    steps = env.steps
    print(f"Final Score: ${steps[-1][0].reward:,.2f}")
    
    # Track sales and expenses across the match
    total_sales = {}
    total_purchases = {}
    
    for s_idx in range(1, len(steps)):
        prev_obs = steps[s_idx-1][0].observation
        cur_obs = steps[s_idx][0].observation
        if not prev_obs or not cur_obs: continue
        
        prev_priv = prev_obs.get("private", {})
        cur_priv = cur_obs.get("private", {})
        prev_shed = prev_priv.get("shed", {})
        cur_shed = cur_priv.get("shed", {})
        
        # Check sales
        for item, p_count in prev_shed.items():
            c_count = cur_shed.get(item, 0)
            if c_count < p_count:
                sold = p_count - c_count
                total_sales[item] = total_sales.get(item, 0) + sold

    print("\n--- ESTIMATED SALES BREAKDOWN ---")
    for k, v in sorted(total_sales.items(), key=lambda x: -x[1]):
        print(f"  * {k}: {v} units")
        
    final_obs = steps[-1][0].observation
    mkt = final_obs.get("market", {})
    prices = mkt.get("prices", {})
    invs = mkt.get("inventory", {})
    print("\n--- FINAL MARKET STATE ---")
    for item in ["MELON", "STRAWBERRY", "MILK", "WOOL", "FERTILIZER", "WHEAT", "CARROT", "TOMATO"]:
        print(f"  * {item:12s} | Price: ${prices.get(item, 0):3d} | Market Inv: {invs.get(item, 0)}")

if __name__ == "__main__":
    run_diagnostic()
