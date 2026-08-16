"""
Visual Game Simulator and Interactive Replayer for Kaggriculture.

Runs a full match between your agent and an opponent, generates an interactive HTML replay,
and launches it in your browser so you can watch every move, crop growth, and market trade.
"""

import argparse
import json
import os
import sys
import webbrowser
import kaggle_environments
from submission import agent as my_agent


def save_html_replay(env, output_html: str):
    """Memory-efficient HTML replay generator."""
    window_kaggle = {
        "debug": False,
        "playing": True,
        "step": 0,
        "controls": True,
        "environment": env.toJSON(),
        "logs": [],
    }

    # Get the raw HTML visualizer template
    raw_renderer = env.html_renderer(env, "html")
    snippet = f"<script>window.kaggle = {json.dumps(window_kaggle)};</script>"

    # Direct search without allocating giant .lower() strings
    head_close = raw_renderer.find("</head>")
    if head_close == -1:
        head_close = raw_renderer.find("</HEAD>")

    if head_close != -1:
        html_out = raw_renderer[:head_close] + snippet + raw_renderer[head_close:]
    else:
        html_out = snippet + raw_renderer

    abs_path = os.path.abspath(output_html)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(html_out)

    return abs_path


def simulate_and_visualize(
    opponent: str = "starter",
    steps: int = 720,
    seed: int = 499739352,
    output_html: str = "replay.html",
    auto_open: bool = True,
    p0_my_agent: bool = True,
):
    print("=" * 70)
    print("        KAGGRICULTURE MATCH SIMULATOR & INTERACTIVE REPLAYER")
    print("=" * 70)

    p0_name = "MyAgent (submission.py)" if p0_my_agent else f"Opponent ({opponent})"
    p1_name = f"Opponent ({opponent})" if p0_my_agent else "MyAgent (submission.py)"
    p0_agent = my_agent if p0_my_agent else opponent
    p1_agent = opponent if p0_my_agent else my_agent

    print(f"Player 0: {p0_name}")
    print(f"Player 1: {p1_name}")
    print(f"Match Length: {steps} steps ({steps // 24} days) | Random Seed: {seed}")
    print("-" * 70)
    print("Simulating match in headless environment...")

    config = {"episodeSteps": steps}
    if seed is not None:
        config["randomSeed"] = seed

    env = kaggle_environments.make("kaggriculture", configuration=config, debug=False)
    env.run([p0_agent, p1_agent])

    # Check match outcome
    final_step = env.steps[-1]
    p0_obs = final_step[0].observation
    p1_obs = final_step[1].observation

    p0_money = p0_obs["farms"][0]["money"]
    p1_money = p1_obs["farms"][1]["money"]

    my_money = p0_money if p0_my_agent else p1_money
    opp_money = p1_money if p0_my_agent else p0_money

    my_farm = p0_obs["farms"][0] if p0_my_agent else p1_obs["farms"][1]
    my_tiles = my_farm.get("tiles", [])
    my_quads = my_farm.get("unlocked_quadrants", ["NW"])
    my_hands = len(my_farm.get("hands", []))

    # Count livestock and plant states on our farm
    animals_active = {}
    plant_counts = {}
    unharvested_ready = 0
    for r in range(len(my_tiles)):
        for c in range(len(my_tiles[r])):
            t = my_tiles[r][c]
            if isinstance(t, dict):
                if t.get("animal"):
                    animals_active[(c, r)] = (t.get("kind"), t.get("animal"))
                elif t.get("kind") == "PLANT":
                    crop = t.get("crop", "UNKNOWN")
                    plant_counts[crop] = plant_counts.get(crop, 0) + 1
                    if t.get("yield_units", 0) > 0:
                        unharvested_ready += 1

    winner = "MyAgent" if my_money > opp_money else ("Opponent" if opp_money > my_money else "TIE")
    delta = my_money - opp_money

    print("\n" + "=" * 70)
    print(f"MATCH RESULT: [{winner.upper()} WINS]  | Margin: {'+' if delta >= 0 else ''}${delta:,.2f}")
    print("=" * 70)
    print(f"  * MyAgent Final Cash : ${my_money:,.2f}")
    print(f"  * Opponent Final Cash: ${opp_money:,.2f}")
    print(f"  * Unlocked Quadrants : {', '.join(my_quads)} ({len(my_quads) * 25} total tiles)")
    print(f"  * Active Animals     : {len(animals_active)} animals on pastures/coops")
    print(f"  * Unharvested Ready  : {unharvested_ready} plants on field (0 is perfect)")
    print(f"  * Shed Inventory     : {p0_obs['private']['shed'] if p0_my_agent else p1_obs['private']['shed']}")
    print("-" * 70)

    # Render interactive HTML replay
    print(f"Generating interactive graphical replay -> '{output_html}'...")
    try:
        saved_path = save_html_replay(env, output_html)
        print(f"[SUCCESS] Replay saved to: file:///{saved_path.replace(chr(92), '/')}")

        if auto_open:
            print("Launching replay in your default web browser...")
            webbrowser.open(f"file:///{saved_path.replace(chr(92), '/')}")
    except Exception as e:
        print(f"[ERROR] Failed to save replay: {e}")

    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kaggriculture Visual Match Simulator")
    parser.add_argument("--opp", default="starter", help="Opponent: 'starter', 'pass', or a python file path")
    parser.add_argument("--steps", type=int, default=720, help="Number of match steps (default: 720 = 30 days)")
    parser.add_argument("--seed", type=int, default=499739352, help="Random seed (default: 499739352)")
    parser.add_argument("--out", default="replay.html", help="Output HTML file path (default: replay.html)")
    parser.add_argument("--no-open", action="store_true", help="Do not automatically launch browser")
    parser.add_argument("--p1", action="store_true", help="Play MyAgent as Player 1 instead of Player 0")

    args = parser.parse_args()
    simulate_and_visualize(
        opponent=args.opp,
        steps=args.steps,
        seed=args.seed,
        output_html=args.out,
        auto_open=not args.no_open,
        p0_my_agent=not args.p1,
    )
