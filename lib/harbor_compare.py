#!/usr/bin/env python3
"""harbor_compare.py - compare two sets of Harbor jobs, paired per task.

  python3 harbor_compare.py --base jobs/A1 jobs/A2 --new jobs/B1
  python3 harbor_compare.py --prune jobs/B1      # move errored trials out, for `harbor jobs resume`

A trial counts only when the verifier gave a reward. Trials that stopped on a usage
limit, a rate limit, an API outage, or a setup error do not count. They are listed so
that you can run them again.
"""

import argparse
import json
import random
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from statistics import median

# Errors that are not the agent's fault. These trials are excluded and can be run again.
INFRA_TYPES = {
    "ApiUsageLimitError",
    "ApiRateLimitError",
    "ApiOverloadedError",
    "ApiInternalServerError",
    "ApiConnectionClosedError",
    "AgentAuthenticationError",
    "CancelledError",
    "ModelNotFoundError",
}
# Subscription limit messages that Harbor can report only as a non-zero exit.
LIMIT_RE = re.compile(
    r"usage limit|limit reached|hit your (usage )?limit|rate.?limit|quota exceeded|"
    r"out of extra usage|credit balance|resets? (at|in) \d",
    re.I,
)


def load_trial(tdir: Path):
    try:
        r = json.loads((tdir / "result.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None
    exc = r.get("exception_info") or {}
    etype, emsg = exc.get("exception_type"), exc.get("exception_message") or ""

    rewards = []
    vr = (r.get("verifier_result") or {}).get("rewards")
    if vr:
        rewards.append(vr.get("reward", sum(vr.values()) / len(vr)))
    else:
        for step in r.get("step_results") or []:
            sr = (step.get("verifier_result") or {}).get("rewards")
            if sr:
                rewards.append(sr.get("reward", sum(sr.values()) / len(sr)))
    reward = sum(rewards) / len(rewards) if rewards else None

    status, reason = "ok", None
    if etype in INFRA_TYPES:
        status, reason = "excluded", etype
    elif etype and _looks_like_limit(tdir, emsg):
        status, reason = "excluded", f"{etype} (looks like a usage limit)"
    elif reward is None:
        status, reason = "excluded", etype or "no reward"

    ar = r.get("agent_result") or {}
    ae = r.get("agent_execution") or {}
    info = r.get("agent_info") or {}
    return {
        "dir": tdir,
        "task": r.get("task_name"),
        "status": status,
        "reason": reason,
        "reward": reward,
        "cost": ar.get("cost_usd"),
        "tok_in": ar.get("n_input_tokens"),
        "seconds": _seconds(ae.get("started_at"), ae.get("finished_at")),
        "agent": f"{info.get('name')} {info.get('version')} {(info.get('model_info') or {}).get('name')}",
    }


def _looks_like_limit(tdir: Path, message: str) -> bool:
    if LIMIT_RE.search(message):
        return True
    agent_dir = tdir / "agent"
    if agent_dir.is_dir():
        for f in agent_dir.glob("*.txt"):
            try:
                with open(f, "rb") as fh:
                    fh.seek(max(0, f.stat().st_size - 4000))
                    if LIMIT_RE.search(fh.read().decode("utf-8", "replace")):
                        return True
            except OSError:
                pass
    return False


def _seconds(a, b):
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
    except (TypeError, ValueError):
        return None


def load_jobs(dirs):
    trials = []
    for d in dirs:
        d = Path(d)
        if not (d / "config.json").exists():
            sys.exit(f"harbor_compare: {d} is not a Harbor job folder (no config.json)")
        for t in sorted(p for p in d.iterdir() if p.is_dir() and (p / "result.json").exists()):
            rec = load_trial(t)
            if rec:
                trials.append(rec)
    return trials


def boot_ci(vals, n=4000, seed=0):
    rng = random.Random(seed)
    k = len(vals)
    means = sorted(sum(rng.choice(vals) for _ in range(k)) / k for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def med(vals):
    vals = [v for v in vals if v is not None]
    return median(vals) if vals else None


def fmt(v, kind):
    if v is None:
        return "-"
    return {"usd": f"${v:.2f}", "s": f"{v:.0f}s", "tok": f"{v / 1000:.0f}k"}[kind]


def compare(a):
    sides = {"base": load_jobs(a.base), "new": load_jobs(a.new)}
    by = {s: {} for s in sides}
    for s, trials in sides.items():
        for t in trials:
            if t["status"] == "ok":
                by[s].setdefault(t["task"], []).append(t)
    tasks = sorted(set(by["base"]) & set(by["new"]))
    if not tasks:
        sys.exit("harbor_compare: no task has counted trials on both sides")

    rate = {(s, t): sum(x["reward"] for x in by[s][t]) / len(by[s][t]) for s in by for t in tasks}
    print(f"{len(tasks)} paired tasks\n")
    print(f"  {'side':<6}{'score':>8}{'95% CI':>16}{'cost/run':>10}{'time':>7}{'tok in':>8}{'runs':>6}")
    for s, label in (("base", a.base_label), ("new", a.new_label)):
        vals = [rate[(s, t)] for t in tasks]
        lo, hi = boot_ci(vals)
        rs = [x for t in tasks for x in by[s][t]]
        print(
            f"  {s:<6}{100 * sum(vals) / len(vals):>7.1f}%{f'[{100 * lo:.0f}, {100 * hi:.0f}]':>16}"
            f"{fmt(med([x['cost'] for x in rs]), 'usd'):>10}{fmt(med([x['seconds'] for x in rs]), 's'):>7}"
            f"{fmt(med([x['tok_in'] for x in rs]), 'tok'):>8}{len(rs):>6}  {label}"
        )

    diffs = [rate[("new", t)] - rate[("base", t)] for t in tasks]
    lo, hi = boot_ci(diffs)
    verdict = "BETTER" if lo > 0 else "WORSE" if hi < 0 else "no clear change (inside the noise)"
    print(
        f"\n  new - base: {100 * sum(diffs) / len(diffs):+.1f} pts, "
        f"95% CI [{100 * lo:+.1f}, {100 * hi:+.1f}] -> {verdict}"
    )

    agents = {s: sorted({x["agent"] for t in tasks for x in by[s][t]}) for s in by}
    if agents["base"] != agents["new"]:
        print(f"  WARNING: agent or model versions differ: {agents}")
    counts = {len(by[s][t]) for s in by for t in tasks}
    if len(counts) > 1:
        print(f"  NOTE: tasks have different numbers of counted runs ({sorted(counts)}).")
    for label, sign in (("better on", 1), ("worse on", -1)):
        moved = [t for t in tasks if sign * (rate[("new", t)] - rate[("base", t)]) > 0]
        if moved:
            print(f"  {label}:")
            for t in moved:
                print(f"    {t}: {rate[('base', t)]:.2f} -> {rate[('new', t)]:.2f}")

    excluded = [t for s in sides for t in sides[s] if t["status"] == "excluded"]
    if excluded:
        kinds = {}
        for t in excluded:
            kinds[t["reason"]] = kinds.get(t["reason"], 0) + 1
        print(f"\n{len(excluded)} trials are not counted: " + ", ".join(f"{k} x{v}" for k, v in sorted(kinds.items())))
        print("To run them again: heval resume <job folder>  (or --prune, then harbor jobs resume)")


def prune(dirs):
    for d in dirs:
        d = Path(d)
        dest = d.parent / f"{d.name}.excluded"
        moved = 0
        for t in load_jobs([d]):
            if t["status"] == "excluded":
                dest.mkdir(exist_ok=True)
                target = dest / t["dir"].name
                if target.exists():
                    target = dest / f"{t['dir'].name}.{datetime.now():%Y%m%d%H%M%S%f}"
                shutil.move(str(t["dir"]), str(target))
                moved += 1
        print(f"{d}: moved {moved} trials to {dest}" if moved else f"{d}: nothing to move")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", nargs="+", help="job folders of the baseline profile")
    ap.add_argument("--new", nargs="+", help="job folders of the profile you changed")
    ap.add_argument("--base-label", default="")
    ap.add_argument("--new-label", default="")
    ap.add_argument("--prune", nargs="+", metavar="JOB", help="move not-counted trials out of these jobs")
    a = ap.parse_args()
    if a.prune:
        prune(a.prune)
    elif a.base and a.new:
        compare(a)
    else:
        ap.error("give --base and --new, or --prune")


if __name__ == "__main__":
    main()
