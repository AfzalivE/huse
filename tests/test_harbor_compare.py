import subprocess
import sys

import pytest

import harbor_compare as hc
from conftest import LIB, make_job, make_trial


def trial(tmp_path, **kw):
    job = tmp_path / "job"
    job.mkdir(exist_ok=True)
    return hc.load_trial(make_trial(job, kw.pop("name", "t1"), "task", **kw))


# ---- which trials count -----------------------------------------------------------------


def test_trial_with_reward_counts(tmp_path):
    t = trial(tmp_path, reward=1)
    assert t["status"] == "ok" and t["reward"] == 1
    assert t["seconds"] == 100 and t["cost"] == 0.5 and t["tok_in"] == 1000


@pytest.mark.parametrize("exc", sorted(hc.INFRA_TYPES))
def test_infra_errors_do_not_count(tmp_path, exc):
    t = trial(tmp_path, exc=exc)
    assert t["status"] == "excluded" and t["reason"] == exc


def test_limit_message_in_agent_log_does_not_count(tmp_path):
    t = trial(
        tmp_path,
        reward=0,
        exc="NonZeroAgentExitCodeError",
        msg="exit 1",
        log="...\nClaude usage limit reached. Your limit resets at 3pm\n",
    )
    assert t["status"] == "excluded" and "usage limit" in t["reason"]


def test_real_agent_failure_counts(tmp_path):
    t = trial(tmp_path, reward=0, exc="NonZeroAgentExitCodeError", msg="exit 1", log="error: build failed\n")
    assert t["status"] == "ok" and t["reward"] == 0


def test_timeout_with_reward_counts(tmp_path):
    t = trial(tmp_path, reward=0, exc="AgentTimeoutError", msg="timed out after 600 seconds")
    assert t["status"] == "ok"


def test_no_reward_does_not_count(tmp_path):
    t = trial(tmp_path, exc="VerifierTimeoutError")
    assert t["status"] == "excluded"


def test_limit_text_without_an_error_still_counts(tmp_path):
    # A task can print "rate limit" in its own output. Only trials with an error can be limit hits.
    t = trial(tmp_path, reward=1, log="testing the rate limiter\n")
    assert t["status"] == "ok"


def test_multi_step_rewards_are_averaged(tmp_path):
    steps = [{"verifier_result": {"rewards": {"reward": 1}}}, {"verifier_result": {"rewards": {"reward": 0}}}]
    t = trial(tmp_path, steps=steps)
    assert t["status"] == "ok" and t["reward"] == 0.5


def test_broken_result_json_is_skipped(tmp_path):
    d = tmp_path / "job" / "t"
    d.mkdir(parents=True)
    (d / "result.json").write_text("{not json")
    assert hc.load_trial(d) is None


def test_load_jobs_ignores_the_job_level_result(tmp_path):
    job = make_job(tmp_path / "j", {"a": [1, 0]})
    assert sorted(t["task"] for t in hc.load_jobs([job])) == ["a", "a"]


def test_load_jobs_rejects_non_job_folders(tmp_path):
    with pytest.raises(SystemExit):
        hc.load_jobs([tmp_path])


# ---- statistics ---------------------------------------------------------------------------


def test_boot_ci_is_deterministic_and_brackets_the_mean():
    vals = [0, 0.5, 1, 1, 0.25, 0.75]
    lo, hi = hc.boot_ci(vals)
    assert (lo, hi) == hc.boot_ci(vals)
    assert lo <= sum(vals) / len(vals) <= hi


def test_boot_ci_of_constant_values():
    assert hc.boot_ci([1.0] * 5) == (1.0, 1.0)


def compare(tmp_path, base, new):
    b = make_job(tmp_path / "base", base)
    n = make_job(tmp_path / "new", new)
    r = subprocess.run(
        [sys.executable, str(LIB / "harbor_compare.py"), "--base", str(b), "--new", str(n)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_verdict_better(tmp_path):
    tasks = [f"t{i}" for i in range(12)]
    out = compare(tmp_path, {t: [0, 0, 0] for t in tasks}, {t: [1, 1, 1] for t in tasks})
    assert "-> BETTER" in out


def test_verdict_worse(tmp_path):
    tasks = [f"t{i}" for i in range(12)]
    out = compare(tmp_path, {t: [1, 1, 1] for t in tasks}, {t: [0, 0, 0] for t in tasks})
    assert "-> WORSE" in out


def test_verdict_inside_the_noise(tmp_path):
    base = {"a": [1, 0], "b": [0, 1], "c": [1, 1], "d": [0, 0]}
    new = {"a": [0, 1], "b": [1, 0], "c": [1, 0], "d": [0, 1]}
    assert "no clear change" in compare(tmp_path, base, new)


def test_only_paired_tasks_are_compared(tmp_path):
    out = compare(tmp_path, {"a": [1], "b": [1]}, {"a": [0], "c": [1]})
    assert "1 paired tasks" in out


def test_excluded_trials_are_reported(tmp_path):
    b = make_job(tmp_path / "base", {"a": [1]})
    n = make_job(tmp_path / "new", {"a": [1]})
    make_trial(n, "limit", "a", exc="ApiUsageLimitError")
    r = subprocess.run(
        [sys.executable, str(LIB / "harbor_compare.py"), "--base", str(b), "--new", str(n)],
        capture_output=True,
        text=True,
    )
    assert "1 trials are not counted: ApiUsageLimitError x1" in r.stdout


# ---- prune --------------------------------------------------------------------------------


def test_prune_moves_only_excluded_trials(tmp_path):
    job = make_job(tmp_path / "job", {"a": [1, 0]})
    make_trial(job, "limit", "a", exc="ApiUsageLimitError")
    make_trial(job, "fail", "a", reward=0, exc="NonZeroAgentExitCodeError", log="boom\n")
    hc.prune([job])
    assert sorted(p.name for p in job.iterdir() if p.is_dir()) == ["a__0", "a__1", "fail"]
    assert (tmp_path / "job.excluded" / "limit").is_dir()


def test_prune_twice_does_not_clash(tmp_path):
    job = make_job(tmp_path / "job", {})
    make_trial(job, "limit", "a", exc="ApiUsageLimitError")
    hc.prune([job])
    make_trial(job, "limit", "a", exc="ApiUsageLimitError")
    hc.prune([job])
    assert len(list((tmp_path / "job.excluded").iterdir())) == 2
