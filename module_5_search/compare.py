"""Compare UCS and A* on every origin/destination pair: `python -m module_5_search.compare`."""
from __future__ import annotations

import itertools

from module_1_simulator.environment import CarEnvironment

from .graph import PREFERENCES
from .route_solver import RouteSolver


def compare(env: CarEnvironment | None = None) -> dict[str, dict[str, float]]:
    env = env or CarEnvironment()
    a, u = RouteSolver.from_env(env, "astar"), RouteSolver.from_env(env, "ucs")
    out = {}
    for pref in PREFERENCES:
        n = same = ea = eu = 0
        for o, d in itertools.permutations(env.state["locations"], 2):
            ra, ru = a.route(o, d, preference=pref), u.route(o, d, preference=pref)
            if ra is None or ru is None:
                same += (ra is None) == (ru is None)
                n += 1
                continue
            n += 1
            same += abs(ra.cost - ru.cost) < 1e-6
            ea += ra.expanded
            eu += ru.expanded
        out[pref] = {"pairs": n, "same_optimal_cost": same / n, "astar_expanded": ea / n, "ucs_expanded": eu / n}
    return out


def main() -> None:
    print(f"{'preference':<10} {'pairs':>5} {'same cost':>9} {'A* exp':>7} {'UCS exp':>7}")
    for p, r in compare().items():
        print(f"{p:<10} {r['pairs']:>5} {r['same_optimal_cost']:>9.2f} {r['astar_expanded']:>7.2f} {r['ucs_expanded']:>7.2f}")


if __name__ == "__main__":
    main()
