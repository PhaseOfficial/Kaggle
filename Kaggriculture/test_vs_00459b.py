"""
Head-to-Head Tournament: Current ML Agent vs Historical Submission (00459b).
Runs 2 matches (Home and Away) and outputs comparative diagnostics & HTML replay.
"""

import sys
import webbrowser
from pathlib import Path
import kaggle_environments

# Import Current Agent
import submission

# Import Historical Agent
sys.path.insert(0, str(Path(__file__).parent / "opponents"))
import submission_00459b


def run_h2h_match(p0_agent, p1_agent, p0_name, p1_name, seed=42, generate_replay=True):
    print(f"\n======================================================================")
    print(f"MATCH: {p0_name} (Player 0) vs {p1_name} (Player 1) [Seed: {seed}]")
    print(f"======================================================================")

    env = kaggle_environments.make("kaggriculture", configuration={"episodeSteps": 720, "randomSeed": seed})
    env.run([p0_agent, p1_agent])

    res_p0 = env.steps[-1][0]
    res_p1 = env.steps[-1][1]
    score_p0 = res_p0.reward
    score_p1 = res_p1.reward

    margin = score_p0 - score_p1
    winner = p0_name if score_p0 > score_p1 else (p1_name if score_p1 > score_p0 else "DRAW")

    print(f"WINNER: [{winner}] | Margin: ${abs(margin):,.2f}")
    print(f"  * {p0_name} (P0) Final Score : ${score_p0:,.2f}")
    print(f"  * {p1_name} (P1) Final Score : ${score_p1:,.2f}")

    obs = env.steps[-1][0].observation
    f0 = obs["farms"][0]
    f1 = obs["farms"][1]
    print(f"  * {p0_name} Land Unlocked    : {', '.join(f0.get('unlocked_quadrants', []))} ({len(f0.get('unlocked_quadrants', []))*25} tiles)")
    print(f"  * {p1_name} Land Unlocked    : {', '.join(f1.get('unlocked_quadrants', []))} ({len(f1.get('unlocked_quadrants', []))*25} tiles)")

    if generate_replay:
        replay_html = env.render(mode="html")
        out_path = Path(__file__).parent / "replay_vs_00459b.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(replay_html)
        print(f"[REPLAY] Saved match visualization to: {out_path.resolve()}")

    return score_p0, score_p1


if __name__ == "__main__":
    print("======================================================================")
    print("      HEAD-TO-HEAD BATTLE: CURRENT ML AGENT VS VERSION 00459b")
    print("======================================================================")

    # Game 1: Current as Player 0, Version 00459b as Player 1
    s0_g1, s1_g1 = run_h2h_match(
        p0_agent=submission.agent,
        p1_agent=submission_00459b.agent,
        p0_name="Current_ML_Agent",
        p1_name="Version_00459b",
        seed=100,
        generate_replay=True,
    )

    # Game 2: Version 00459b as Player 0, Current as Player 1 (Swap sides)
    s0_g2, s1_g2 = run_h2h_match(
        p0_agent=submission_00459b.agent,
        p1_agent=submission.agent,
        p0_name="Version_00459b",
        p1_name="Current_ML_Agent",
        seed=100,
        generate_replay=False,
    )

    print("\n======================================================================")
    print("                     OVERALL TOURNAMENT SUMMARY")
    print("======================================================================")
    current_total = s0_g1 + s1_g2
    hist_total = s1_g1 + s0_g2
    diff = current_total - hist_total

    print(f"Current ML Agent Cumulative Score : ${current_total:,.2f}")
    print(f"Historical 00459b Cumulative Score: ${hist_total:,.2f}")
    print(f"Total Advantage Margin            : +${diff:,.2f} ({'+' if diff > 0 else ''}{(diff / max(1, hist_total))*100:.1f}%)")
    print("======================================================================\n")
