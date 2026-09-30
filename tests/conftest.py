"""Shared fixtures. Every test runs in a temporary HOME. Nothing touches the real home folder."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BIN = REPO / "bin"
LIB = REPO / "lib"
sys.path.insert(0, str(LIB))

# The bash that runs the scripts. CI sets TEST_BASH=/bin/bash on macOS to test Bash 3.2.
TEST_BASH = os.environ.get("TEST_BASH", "bash")

PROFILE_VARS = (
    "HARNESS_ROOT",
    "HARNESS_PROFILE",
    "HUSE_SUBSHELL",
    "CLAUDE_CONFIG_DIR",
    "CODEX_HOME",
    "PI_CODING_AGENT_DIR",
    "HEVAL_CONF",
    "HEVAL_ENV",
    "JOBS_DIR",
    "HEVAL_HOME",
    "HEVAL_SKIP_LOGIN_CHECK",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_API_KEY",
    "CODEX_AUTH_JSON_PATH",
    "CODEX_FORCE_AUTH_JSON",
    "PI_AUTH_JSON_PATH",
    "ZDOTDIR",
)

# Fake codex and pi: print what they see. They let the tests check huse without the real programs.
# printf, not echo: dash's echo changes backslashes.
FAKE_AGENT = """#!/bin/sh
printf 'TOOL=%s\\n' NAME
printf 'HOME=%s\\n' "$HOME"
printf 'CODEX_HOME=%s\\n' "${CODEX_HOME:-}"
printf 'PI_DIR=%s\\n' "${PI_CODING_AGENT_DIR:-}"
for a in "$@"; do printf 'ARG=%s\\n' "$a"; done
"""

FAKE_HARBOR = """#!/bin/sh
# Fake harbor: record the arguments and the environment, then succeed.
printf '%s\\n' "$@" > "$FAKE_HARBOR_ARGS"
env > "$FAKE_HARBOR_ENV"
echo "fake harbor: $1"
"""


@pytest.fixture
def home(tmp_path):
    """A home folder with a space in its path and a normal harness setup."""
    h = tmp_path / "my home"
    for d in (".claude", ".codex", ".pi/agent", ".agents/skills/orig"):
        (h / d).mkdir(parents=True)
    (h / ".agents/skills/orig/SKILL.md").write_text("---\nname: orig\n---\n")
    return h


@pytest.fixture
def fakebin(tmp_path):
    d = tmp_path / "fakebin"
    d.mkdir()
    harbor = d / "harbor"
    harbor.write_text(FAKE_HARBOR)
    harbor.chmod(0o755)
    for tool in ("codex", "pi"):
        f = d / tool
        f.write_text(FAKE_AGENT.replace("NAME", tool))
        f.chmod(0o755)
    return d


@pytest.fixture
def env(home, fakebin, tmp_path):
    e = {k: v for k, v in os.environ.items() if k not in PROFILE_VARS}
    e.update(
        HOME=str(home),
        PATH=f"{BIN}{os.pathsep}{fakebin}{os.pathsep}{os.environ['PATH']}",
        SHELL=shutil.which("bash") or "/bin/bash",
        FAKE_HARBOR_ARGS=str(tmp_path / "harbor.args"),
        FAKE_HARBOR_ENV=str(tmp_path / "harbor.env"),
    )
    return e


def run(tool, *args, env, input=None, timeout=30, check=False):
    """Run bin/<tool> with TEST_BASH."""
    r = subprocess.run(
        [TEST_BASH, str(BIN / tool), *map(str, args)],
        env=env,
        input=input,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and r.returncode != 0:
        raise AssertionError(f"{tool} {args} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


def huse(*args, **kw):
    return run("huse", *args, **kw)


def heval(*args, **kw):
    return run("heval", *args, **kw)


def seen(output: str) -> dict[str, list[str]]:
    """Parse the output of a fake agent: KEY=value lines."""
    out: dict[str, list[str]] = {}
    for line in output.splitlines():
        k, sep, v = line.partition("=")
        if sep:
            out.setdefault(k, []).append(v)
    return out


def harbor_args(env) -> list[str]:
    return Path(env["FAKE_HARBOR_ARGS"]).read_text().splitlines()


def harbor_env(env) -> dict[str, str]:
    out = {}
    for line in Path(env["FAKE_HARBOR_ENV"]).read_text().splitlines():
        k, _, v = line.partition("=")
        out[k] = v
    return out


def make_trial(job: Path, name: str, task: str, reward=None, exc=None, msg="", log=None, cost=0.5, steps=None):
    """Write one trial folder in the shape of Harbor's TrialResult (fields that we read)."""
    d = job / name
    d.mkdir(parents=True)
    result = {
        "task_name": task,
        "trial_name": name,
        "agent_info": {"name": "claude-code", "version": "1.0.0", "model_info": {"name": "m"}},
        "agent_result": {"n_input_tokens": 1000, "n_output_tokens": 100, "cost_usd": cost},
        "agent_execution": {"started_at": "2026-01-01T10:00:00", "finished_at": "2026-01-01T10:01:40"},
        "verifier_result": {"rewards": {"reward": reward}} if reward is not None else None,
        "exception_info": {"exception_type": exc, "exception_message": msg} if exc else None,
        "step_results": steps,
    }
    (d / "result.json").write_text(json.dumps(result))
    if log is not None:
        (d / "agent").mkdir()
        (d / "agent" / "agent.txt").write_text(log)
    return d


def make_job(path: Path, rates: dict[str, list[int]]):
    """A fake Harbor job folder. rates: task -> list of rewards (one per attempt)."""
    path.mkdir(parents=True)
    (path / "config.json").write_text("{}")
    (path / "result.json").write_text("{}")  # the job-level result is not a trial
    for task, rewards in rates.items():
        for i, r in enumerate(rewards):
            make_trial(path, f"{task}__{i}", task, reward=r)
    return path
