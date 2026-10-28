"""Scenario suite, Pass@3 / Pass^3 and the ablation table.

    python -m module_10_integration.run_experiments            # writes RESULTS.md
    python -m module_10_integration.run_experiments --trials 3 --configs full_fixed full_rl
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .config import ABLATIONS
from .metrics import HEADER, run_trial, summarise
from .scenarios import SCENARIOS


def run(configs: list[str], trials: int = 3, rl_agent=None):
    out = {}
    for name in configs:
        cfg = ABLATIONS[name]
        agent = rl_agent
        if cfg.policy == "rl" and agent is None:
            from module_8_rl.evaluate import train_agent
            agent = rl_agent = train_agent(episodes=60000)
        res = {sc.id: [run_trial(sc, cfg, seed=k, perturb=k > 0, rl_agent=agent) for k in range(trials)]
               for sc in SCENARIOS}
        out[name] = (summarise(name, res), res)
    return out


def to_markdown(results, trials: int) -> str:
    lines = ["# Module 10 results", "",
             f"{len(SCENARIOS)} scenarios x {trials} trials (trial 1 uses the base state, later trials perturb "
             "traffic and road speeds with a seed). Pass@3: success in at least one trial; Pass^3: success in all.",
             "", "## Ablation", "", HEADER]
    lines += [s.row() for s, _ in results.values()]
    cats = sorted({c for s, _ in results.values() for c in s.by_category})
    lines += ["", "## Success by category", "", "| configuration | " + " | ".join(cats) + " |",
              "|---" * (len(cats) + 1) + "|"]
    for s, _ in results.values():
        lines.append(f"| {s.config} | " + " | ".join(f"{s.by_category.get(c, 0):.2f}" for c in cats) + " |")
    best = "full_rl" if "full_rl" in results else next(iter(results))
    lines += ["", f"## Per-scenario ({best})", "", "| scenario | category | trials passed | questions |",
              "|---|---|---|---|"]
    for sid, ts in results[best][1].items():
        lines.append(f"| {sid} | {ts[0].category} | {sum(t.success for t in ts)}/{len(ts)} | "
                     f"{ts[0].questions} |")
    lines += ["", "## Example transcripts (full_fixed, trial 1)", ""]
    ref = results.get("full_fixed", results[best])[1]
    for sid in ["ambig_tea_cafe", "multi_route_charge_notify", "infeasible_cuttack", "change_waypoint_fails",
                "unsafe_windows_highway", "cap_massage"]:
        if sid in ref:
            lines.append(f"**{sid}**\n")
            for u, r in ref[sid][0].transcript:
                lines.append(f"- driver: {u}\n- copilot: {r}")
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--configs", nargs="*", default=list(ABLATIONS))
    ap.add_argument("--out", default=str(Path(__file__).with_name("RESULTS.md")))
    a = ap.parse_args()
    results = run(a.configs, a.trials)
    md = to_markdown(results, a.trials)
    Path(a.out).write_text(md)
    print(md)


if __name__ == "__main__":
    main()
