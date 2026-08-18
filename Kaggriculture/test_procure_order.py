"""
Verification test to strictly verify that all 12 animals (8 Cows + 4 Sheep) 
are procured before Quadrant 3 (SW) is unlocked.
"""

import kaggle_environments
import submission

def run_verification():
    env = kaggle_environments.make("kaggriculture", configuration={"episodeSteps": 720})
    env.run([submission.agent, "starter"])
    
    steps = env.steps
    print(f"Total Steps: {len(steps)}")
    final_reward = steps[-1][0].reward
    print(f"Final Score: ${final_reward:,.2f}")
    
    # Check the history for land purchase and animal counts
    for s_idx, step_data in enumerate(steps):
        agent_obs = step_data[0].observation
        if not agent_obs: continue
        farms = agent_obs.get("farms", [])
        if not farms: continue
        my_farm = farms[0]
        unlocked = my_farm.get("unlocked_quadrants", [])
        day = agent_obs.get("day", 0)
        hour = agent_obs.get("hour", 0)
        
        # Check when SW is unlocked
        if "SW" in unlocked:
            prev_unlocked = steps[s_idx - 1][0].observation.get("farms", [{}])[0].get("unlocked_quadrants", [])
            if "SW" not in prev_unlocked:
                print(f"\n[EVENT] Quadrant 3 (SW) was unlocked on Day {day}, Hour {hour} (Step {s_idx})")
                
                # Check animal count at that moment
                tiles = my_farm.get("tiles", [])
                cows_on_field = 0
                sheep_on_field = 0
                for row in tiles:
                    for t in row:
                        if isinstance(t, dict):
                            if t.get("animal") == "COW": cows_on_field += 1
                            elif t.get("animal") == "SHEEP": sheep_on_field += 1
                
                priv = agent_obs.get("private", {})
                shed = priv.get("shed", {})
                invs = priv.get("inventories", [])
                total_cows = cows_on_field + shed.get("COW", 0) + sum(inv.get("COW", 0) for inv in invs)
                total_sheep = sheep_on_field + shed.get("SHEEP", 0) + sum(inv.get("SHEEP", 0) for inv in invs)
                
                print(f"  * Cows held: {total_cows}/8 (on field: {cows_on_field})")
                print(f"  * Sheep held: {total_sheep}/4 (on field: {sheep_on_field})")
                assert total_cows >= 8 and total_sheep >= 4, "ERROR: SW unlocked before all 12 animals were procured!"
                print("  [SUCCESS] All 12 animals were fully procured before Quadrant 3 (SW) was unlocked!")
                break
    else:
        print("Note: Quadrant 3 (SW) was not unlocked in this match (or unlocked with farm fully established).")

if __name__ == "__main__":
    run_verification()
