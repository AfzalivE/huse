import os
import re
import shutil
import subprocess

import pytest

from conftest import BIN, TEST_BASH, harbor_args, harbor_env, heval, make_job, make_trial

CONF = """DATASET="terminal-bench/terminal-bench@4.0.0"
N_TASKS=30
EXCLUDE_TASKS=(bad-task "other task")
ATTEMPTS=3
CONCURRENCY=2
ENV_TYPE=docker
CLAUDE_MODEL="anthropic/model-x"
CODEX_MODEL="openai/model-y"
PI_MODEL="openai-codex/model-z"
CLAUDE_VERSION="9.9.9"
CODEX_VERSION=""
PI_VERSION=""
"""
SUITE = "terminal-bench-terminal-bench-4.0.0"


@pytest.fixture
def conf(tmp_path):
    p = tmp_path / "eval.conf"
    p.write_text(CONF)
    return p


@pytest.fixture
def henv(env, conf, home):
    """heval environment with two profiles: base (skills and instructions for each harness) and bare (empty)."""
    base = home / ".harness/profiles/base"
    for part, instr in (("claude", "CLAUDE.md"), ("codex", "AGENTS.md"), ("pi", "AGENTS.md")):
        (base / part / "skills/s1").mkdir(parents=True)
        (base / part / "skills/s1/SKILL.md").write_text("---\n")
        (base / part / instr).write_text("# rules\n")
    for part in ("claude", "codex", "pi"):
        (home / ".harness/profiles/bare" / part).mkdir(parents=True)
    shutil.rmtree(home / ".agents/skills/orig")  # most tests: no global skills
    logins = home / "logins"
    logins.mkdir()
    (logins / "codex.json").write_text("{}")
    (logins / "pi.json").write_text('{"openai-codex": {"type": "oauth"}}')
    return dict(
        env,
        HEVAL_CONF=str(conf),
        CLAUDE_CODE_OAUTH_TOKEN="test-token",
        CODEX_AUTH_JSON_PATH=str(logins / "codex.json"),
        PI_AUTH_JSON_PATH=str(logins / "pi.json"),
    )


def opt(args, flag):
    """All values given after a flag."""
    return [args[i + 1] for i, a in enumerate(args) if a == flag]


# ---- config checks ------------------------------------------------------------------------


@pytest.mark.parametrize("cmd", [("check",), ("run", "claude", "base"), ("compare", "claude", "a", "b")])
def test_placeholder_dataset_stops_every_command(henv, conf, cmd):
    conf.write_text(CONF.replace("@4.0.0", "@<version>"))
    r = heval(*cmd, env=henv)
    assert r.returncode == 1
    assert "set DATASET" in r.stderr
    assert not os.path.exists(henv["FAKE_HARBOR_ARGS"])


def test_placeholder_model_stops_run(henv, conf):
    conf.write_text(CONF.replace("anthropic/model-x", "anthropic/<model-id>"))
    r = heval("run", "claude", "base", env=henv)
    assert r.returncode == 1 and "claude model" in r.stderr


def test_missing_conf(henv, tmp_path):
    r = heval("check", env=dict(henv, HEVAL_CONF=str(tmp_path / "nope.conf")))
    assert r.returncode == 1 and "missing" in r.stderr


def test_unknown_profile_and_harness(henv):
    assert "no profile 'nope'" in heval("run", "claude", "nope", env=henv).stderr
    assert "claude, codex, or pi" in heval("run", "gemini", "base", env=henv).stderr


# ---- the harbor command -------------------------------------------------------------------


def test_run_claude_builds_expected_command(henv, home):
    r = heval("run", "claude", "base", "--dry-run", env=henv)
    assert r.returncode == 0, r.stderr
    a = harbor_args(henv)
    assert a[0] == "run"
    assert opt(a, "-d") == ["terminal-bench/terminal-bench@4.0.0"]
    assert opt(a, "-k") == ["3"] and opt(a, "-n") == ["2"] and opt(a, "-l") == ["30"]
    assert opt(a, "-x") == ["bad-task", "other task"]
    assert opt(a, "-a") == ["harbor_profile_agents:ClaudeCodeProfile"]
    assert opt(a, "-m") == ["anthropic/model-x"]
    assert opt(a, "-o") == [str(home / ".heval/jobs")]
    assert re.fullmatch(rf"{SUITE}__claude__base__\d{{8}}-\d{{6}}", opt(a, "--job-name")[0])
    base = home / ".harness/profiles/base"
    assert opt(a, "--skill") == [str(base / "claude/skills")]
    assert opt(a, "--ae") == [f"HARNESS_INSTRUCTIONS={base}/claude/CLAUDE.md"]
    assert opt(a, "--ak") == ["version=9.9.9"]
    assert a[-1] == "--dry-run"  # extra arguments go to harbor


@pytest.mark.parametrize(
    "harness,cls,model",
    [
        ("codex", "CodexProfile", "openai/model-y"),
        ("pi", "PiProfile", "openai-codex/model-z"),
    ],
)
def test_run_other_harnesses(henv, home, harness, cls, model):
    heval("run", harness, "base", env=henv, check=True)
    a = harbor_args(henv)
    base = home / ".harness/profiles/base"
    assert opt(a, "-a") == [f"harbor_profile_agents:{cls}"] and opt(a, "-m") == [model]
    assert opt(a, "--skill") == [str(base / harness / "skills")]
    assert opt(a, "--ae") == [f"HARNESS_INSTRUCTIONS={base}/{harness}/AGENTS.md"]
    assert opt(a, "--ak") == []  # no version pinned, no config file


def test_config_file_is_sent(henv, home):
    base = home / ".harness/profiles/base"
    (base / "claude/eval-settings.json").write_text("{}")
    heval("run", "claude", "base", env=henv, check=True)
    assert f"config={base}/claude/eval-settings.json" in opt(harbor_args(henv), "--ak")


def test_warns_about_at_imports(henv, home):
    (home / ".harness/profiles/base/claude/CLAUDE.md").write_text("@~/.agents/AGENTS.md\n")
    r = heval("run", "claude", "base", env=henv, check=True)
    assert "@ imports" in r.stderr


@pytest.mark.parametrize("harness", ["codex", "pi"])
def test_global_skills_are_sent_for_codex_and_pi(henv, home, harness):
    # Codex and pi read ~/.agents/skills in every profile, so the run must get them too.
    (home / ".agents/skills/g1").mkdir(parents=True)
    (home / ".agents/skills/g1/SKILL.md").write_text("---\n")
    r = heval("run", harness, "bare", env=henv, check=True)
    assert opt(harbor_args(henv), "--skill") == [str(home / ".agents/skills")]
    assert "huse setup" in r.stderr


def test_global_skills_are_not_sent_for_claude(henv, home):
    (home / ".agents/skills/g1").mkdir(parents=True)
    (home / ".agents/skills/g1/SKILL.md").write_text("---\n")
    heval("run", "claude", "bare", env=henv, check=True)
    assert opt(harbor_args(henv), "--skill") == []


def test_skill_links_to_the_store_are_sent(henv, home):
    s1 = home / ".harness/skills/linked"
    s1.mkdir(parents=True)
    (s1 / "SKILL.md").write_text("---\n")
    (home / ".harness/profiles/bare/codex/skills").mkdir()
    (home / ".harness/profiles/bare/codex/skills/linked").symlink_to(s1)
    heval("run", "codex", "bare", env=henv, check=True)
    assert opt(harbor_args(henv), "--skill") == [str(home / ".harness/profiles/bare/codex/skills")]


def test_empty_profile_sends_no_skills_or_instructions(henv):
    heval("run", "codex", "bare", env=henv, check=True)
    a = harbor_args(henv)
    assert opt(a, "--skill") == [] and opt(a, "--ae") == []


def test_system_profile_uses_the_normal_folders(henv, home):
    (home / ".codex/skills/x").mkdir(parents=True)
    (home / ".codex/skills/x/SKILL.md").write_text("---\n")
    (home / ".codex/AGENTS.md").write_text("# rules\n")
    heval("run", "codex", "system", env=henv, check=True)
    a = harbor_args(henv)
    assert opt(a, "--skill") == [str(home / ".codex/skills")]
    assert opt(a, "--ae") == [f"HARNESS_INSTRUCTIONS={home}/.codex/AGENTS.md"]


def test_check_runs_oracle(henv):
    heval("check", env=henv, check=True)
    a = harbor_args(henv)
    assert opt(a, "-a") == ["oracle"] and opt(a, "-x") == ["bad-task", "other task"]
    assert re.fullmatch(rf"{SUITE}__oracle__\d{{8}}-\d{{6}}", opt(a, "--job-name")[0])


# A fake harbor that writes an oracle job: task "ok" passes, task "broken" fails.
FAKE_ORACLE_HARBOR = """#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
job = os.path.join(a[a.index("-o") + 1], a[a.index("--job-name") + 1])
os.makedirs(job)
open(os.path.join(job, "config.json"), "w").write("{}")
for task, reward in (("ok", 1), ("broken", 0)):
    os.makedirs(os.path.join(job, task))
    r = {"task_name": task, "verifier_result": {"rewards": {"reward": reward}}}
    open(os.path.join(job, task, "result.json"), "w").write(json.dumps(r))
sys.exit(int(os.environ.get("FAKE_HARBOR_EXIT", "0")))
"""


@pytest.mark.parametrize("code", [0, 3])
def test_check_prints_tasks_that_failed_the_oracle(henv, fakebin, code):
    (fakebin / "harbor").write_text(FAKE_ORACLE_HARBOR)
    r = heval("check", env=dict(henv, FAKE_HARBOR_EXIT=str(code)))
    assert r.returncode == code
    assert r.stdout.splitlines()[-1] == '  "broken"'
    assert "1 tasks failed the oracle run" in r.stderr


def test_check_dry_run_prints_no_failures(henv):
    r = heval("check", "--dry-run", env=henv, check=True)
    assert "oracle run" not in r.stderr


# ---- env file, PYTHONPATH, symlinks -------------------------------------------------------


def test_env_file_is_loaded_and_open_modes_warn(henv, home):
    f = home / ".heval/eval.env"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("CLAUDE_CODE_OAUTH_TOKEN=tok-123\nCODEX_AUTH_JSON_PATH=$HOME/x.json\n")
    f.chmod(0o644)
    r = heval("check", env=henv, check=True)
    assert "other users can read" in r.stderr
    he = harbor_env(henv)
    assert he["CLAUDE_CODE_OAUTH_TOKEN"] == "tok-123"
    assert he["CODEX_AUTH_JSON_PATH"] == f"{home}/x.json"
    f.chmod(0o600)
    assert "other users can read" not in heval("check", env=henv, check=True).stderr


def test_pythonpath_points_at_lib(henv):
    heval("check", env=henv, check=True)
    assert harbor_env(henv)["PYTHONPATH"].split(os.pathsep)[0] == str(BIN.parent / "lib")


def test_works_through_a_symlink(henv, tmp_path):
    link_dir = tmp_path / "linkbin"
    link_dir.mkdir()
    (link_dir / "heval").symlink_to(BIN / "heval")
    r = subprocess.run(
        [TEST_BASH, str(link_dir / "heval"), "check"], env=henv, capture_output=True, text=True, timeout=30
    )
    assert r.returncode == 0, r.stderr
    assert harbor_env(henv)["PYTHONPATH"].split(os.pathsep)[0] == str(BIN.parent / "lib")


# ---- jobs, resume, compare ----------------------------------------------------------------


def jobs_dir(home):
    return home / ".heval/jobs"


def test_jobs_hides_excluded(henv, home):
    make_job(jobs_dir(home) / f"{SUITE}__claude__base__20260101-000000", {"t": [1]})
    (jobs_dir(home) / f"{SUITE}__claude__base__20260101-000000.excluded").mkdir()
    out = heval("jobs", env=henv, check=True).stdout.split()
    assert out == [f"{SUITE}__claude__base__20260101-000000"]


def test_resume_by_name_prunes_then_calls_harbor(henv, home):
    job = make_job(jobs_dir(home) / f"{SUITE}__claude__base__20260101-000000", {"t": [1]})
    make_trial(job, "limit", "t", exc="ApiUsageLimitError", msg="You've hit your usage limit")
    r = heval("resume", job.name, env=henv, check=True)
    assert "moved 1 trials" in r.stdout
    assert harbor_args(henv) == ["jobs", "resume", "-p", str(job)]
    assert (job.parent / f"{job.name}.excluded" / "limit").is_dir()


def test_resume_unknown_job(henv):
    r = heval("resume", "nope", env=henv)
    assert r.returncode == 1 and "no job 'nope'" in r.stderr


def test_compare_uses_all_jobs_of_each_profile(henv, home):
    j = jobs_dir(home)
    make_job(j / f"{SUITE}__claude__base__20260101-000000", {"a": [0, 0], "b": [1, 0]})
    make_job(j / f"{SUITE}__claude__base__20260102-000000", {"a": [0], "b": [1]})
    make_job(j / f"{SUITE}__claude__new__20260103-000000", {"a": [1, 1, 1], "b": [1, 1, 1]})
    make_job(j / f"{SUITE}__codex__new__20260103-000000", {"a": [0]})  # other harness: ignored
    r = heval("compare", "claude", "base", "new", env=henv, check=True)
    assert "2 paired tasks" in r.stdout
    assert re.search(r"base\s+33\.3%", r.stdout) and re.search(r"new\s+100\.0%", r.stdout)


def test_compare_without_jobs(henv):
    r = heval("compare", "claude", "base", "new", env=henv)
    assert r.returncode == 1 and "no claude jobs for profile 'base'" in r.stderr


# ---- where heval keeps its data -------------------------------------------------------------


def snapshot(folder):
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


def test_heval_never_writes_in_harness_root(henv, home):
    before = snapshot(home / ".harness")
    heval("check", env=henv, check=True)
    heval("run", "claude", "base", env=henv, check=True)
    job = make_job(jobs_dir(home) / f"{SUITE}__claude__base__20260101-000000", {"t": [1]})
    make_trial(job, "limit", "t", exc="ApiUsageLimitError")
    heval("resume", job.name, env=henv, check=True)
    assert snapshot(home / ".harness") == before


def test_heval_home_moves_logins_and_jobs(henv, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "eval.env").write_text("CLAUDE_CODE_OAUTH_TOKEN=from-other\n")
    (other / "eval.env").chmod(0o600)
    e = dict(henv, HEVAL_HOME=str(other))
    heval("run", "claude", "base", env=e, check=True)
    assert opt(harbor_args(e), "-o") == [str(other / "jobs")]
    assert harbor_env(e)["CLAUDE_CODE_OAUTH_TOKEN"] == "from-other"


def test_note_about_files_in_the_old_place(henv, home):
    (home / ".harness/eval.env").write_text("X=1\n")
    (home / ".harness/jobs").mkdir()
    r = heval("check", env=henv, check=True)
    assert "heval now keeps its files in" in r.stderr
    assert f"{home}/.harness/eval.env" in r.stderr and f"{home}/.harness/jobs" in r.stderr
    assert "X" not in harbor_env(henv)  # the old file is not loaded


def test_no_note_without_old_files(henv):
    assert "heval now keeps" not in heval("check", env=henv, check=True).stderr


# ---- login check before a run -------------------------------------------------------------


def without(env, *names):
    return {k: v for k, v in env.items() if k not in names}


@pytest.mark.parametrize(
    "harness,remove,message",
    [
        ("claude", ("CLAUDE_CODE_OAUTH_TOKEN",), "no Claude login"),
        ("codex", ("CODEX_AUTH_JSON_PATH",), "no Codex login"),
        ("pi", ("PI_AUTH_JSON_PATH",), "no pi login"),
    ],
)
def test_run_stops_without_a_login(henv, harness, remove, message):
    r = heval("run", harness, "base", env=without(henv, *remove))
    assert r.returncode == 1 and message in r.stderr
    assert not os.path.exists(henv["FAKE_HARBOR_ARGS"])  # no job started


@pytest.mark.parametrize("harness,var", [("codex", "CODEX_AUTH_JSON_PATH"), ("pi", "PI_AUTH_JSON_PATH")])
def test_run_stops_when_the_login_file_is_missing(henv, tmp_path, harness, var):
    r = heval("run", harness, "base", env=dict(henv, **{var: str(tmp_path / "nope.json")}))
    assert r.returncode == 1 and "missing file" in r.stderr


def test_pi_login_without_openai_codex_warns(henv, home):
    (home / "logins/pi.json").write_text('{"anthropic": {}}')
    r = heval("run", "pi", "base", env=henv, check=True)
    assert "no openai-codex login" in r.stderr


def test_pi_with_an_api_key_provider_needs_no_login_file(henv, conf):
    conf.write_text(CONF.replace("openai-codex/model-z", "openrouter/model-z"))
    heval("run", "pi", "base", env=without(henv, "PI_AUTH_JSON_PATH"), check=True)


@pytest.mark.parametrize(
    "harness,alternative",
    [
        ("claude", {"ANTHROPIC_API_KEY": "k"}),
        ("codex", {"OPENAI_API_KEY": "k"}),
        ("codex", {"CODEX_FORCE_AUTH_JSON": "1"}),
    ],
)
def test_api_keys_also_count_as_logins(henv, harness, alternative):
    e = without(henv, "CLAUDE_CODE_OAUTH_TOKEN", "CODEX_AUTH_JSON_PATH")
    heval("run", harness, "base", env=dict(e, **alternative), check=True)


def test_login_check_can_be_skipped(henv):
    e = dict(without(henv, "CLAUDE_CODE_OAUTH_TOKEN"), HEVAL_SKIP_LOGIN_CHECK="1")
    heval("run", "claude", "base", env=e, check=True)


def test_logins_from_eval_env_count(henv, home):
    f = home / ".heval/eval.env"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("CLAUDE_CODE_OAUTH_TOKEN=from-file\n")
    f.chmod(0o600)
    heval("run", "claude", "base", env=without(henv, "CLAUDE_CODE_OAUTH_TOKEN"), check=True)
