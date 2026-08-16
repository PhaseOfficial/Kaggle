"""Tournament and simulation evaluation harness for Kaggriculture agents."""

import time
from kaggle_environments import make
from main import agent as my_agent


def run_single_match(agent_a, agent_b, steps: int = 720, debug: bool = False) -> tuple[float, float, str]:
    """Runs a single match between two agents and returns (score_a, score_b, outcome)."""
    env = make("kaggriculture", configuration={"episodeSteps": steps}, debug=debug)
    env.run([agent_a, agent_b])
    final_step = env.steps[-1]
    score_a = final_step[0].reward or 0
    score_b = final_step[1].reward or 0

    if score_a > score_b:
        outcome = "A_WINS"
    elif score_b > score_a:
        outcome = "B_WINS"
    else:
        outcome = "TIE"

    return score_a, score_b, outcome


def run_benchmark(num_matches: int = 5, opponent_name: str = "starter", steps: int = 720):
    """Runs a multi-match benchmark between my_agent and a baseline opponent."""
    print("=" * 65)
    print(f"Running Kaggriculture Benchmark: MyAgent vs '{opponent_name}' ({num_matches} matches, {steps} steps)")
    print("=" * 65)

    wins = 0
    losses = 0
    ties = 0
    scores_my = []
    scores_opp = []

    start_time = time.time()

    for m in range(num_matches):
        # Alternate sides (Player 0 vs Player 1)
        as_player_0 = (m % 2 == 0)
        p0 = my_agent if as_player_0 else opponent_name
        p1 = opponent_name if as_player_0 else my_agent

        score_0, score_1, outcome = run_single_match(p0, p1, steps=steps)

        my_score = score_0 if as_player_0 else score_1
        opp_score = score_1 if as_player_0 else score_0

        scores_my.append(my_score)
        scores_opp.append(opp_score)

        if my_score > opp_score:
            res = "WIN "
            wins += 1
        elif my_score < opp_score:
            res = "LOSS"
            losses += 1
        else:
            res = "TIE "
            ties += 1

        side = "P0" if as_player_0 else "P1"
        print(f"Match {m+1:>2}/{num_matches}: [{res}] MyAgent ({side}) = ${my_score:,.0f} | Opponent = ${opp_score:,.0f}")

    elapsed = time.time() - start_time
    avg_my = sum(scores_my) / len(scores_my) if scores_my else 0
    avg_opp = sum(scores_opp) / len(scores_opp) if scores_opp else 0
    win_rate = (wins + 0.5 * ties) / num_matches * 100 if num_matches > 0 else 0

    print("-" * 65)
    print(f"Results Summary ({elapsed:.1f}s total):")
    print(f"Record   : {wins} Wins, {losses} Losses, {ties} Ties ({win_rate:.1f}% Score Rate)")
    print(f"Avg Score: MyAgent = ${avg_my:,.0f} | Opponent = ${avg_opp:,.0f} (Delta: +${avg_my - avg_opp:,.0f})")
    print("=" * 65)


if __name__ == "__main__":
    # Run against built-in starter baseline
    run_benchmark(num_matches=4, opponent_name="starter", steps=720)
