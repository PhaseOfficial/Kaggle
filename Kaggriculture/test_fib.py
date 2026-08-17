"""
Testing Fibonacci-based dynamic hiring engine.
"""

def get_hire_cost(n: int) -> int:
    fibs = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377]
    if n < len(fibs):
        return fibs[n]
    a, b = fibs[-2], fibs[-1]
    for _ in range(n - len(fibs) + 1):
        a, b = b, a + b
    return b

def get_cumulative_hire_cost(num_hands: int) -> int:
    return sum(get_hire_cost(i) for i in range(num_hands))

for h in range(1, 14):
    print(f"Hand {h:2d} | Next Cost: ${get_hire_cost(h-1):3d} | Total Daily Wage: ${get_cumulative_hire_cost(h):3d}")
