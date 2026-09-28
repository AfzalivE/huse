"""Tests that need the harbor package. They are skipped when harbor is not installed.

lib/harbor_profile_agents.py uses Harbor internals, so these tests pin the Harbor version
that the code was written for. Run them after each Harbor upgrade:  pytest -m harbor
"""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import LIB

pytestmark = pytest.mark.harbor
harbor = pytest.importorskip("harbor")

from harbor.agents.installed.claude_code import ClaudeCode  # noqa: E402
from harbor.agents.installed.codex import Codex  # noqa: E402
from harbor.agents.installed.pi import Pi  # noqa: E402

import harbor_profile_agents as hpa  # noqa: E402


class FakeEnvironment:
    default_user = "agent"

    def __init__(self):
        self.calls = []

    async def upload_file(self, source, target):
        self.calls.append(("upload", str(source), target))

    async def exec(self, command, user=None, env=None, cwd=None, timeout_sec=None, **kw):
        self.calls.append(("exec", user, command))

        class Result:
            return_code, stdout, stderr = 0, "", ""

        return Result()


async def _no_setup(self, environment):
    pass


def run_setup(cls, parent, model, tmp_path, extra_env):
    agent = cls(logs_dir=tmp_path / "logs", model_name=model, extra_env=extra_env)
    env = FakeEnvironment()
    with patch.object(parent, "setup", _no_setup):
        asyncio.run(agent.setup(env))
    return env.calls


@pytest.fixture
def files(tmp_path):
    instr = tmp_path / "AGENTS.md"
    instr.write_text("# rules\n")
    auth = tmp_path / "auth.json"
    auth.write_text("{}")
    return {"HARNESS_INSTRUCTIONS": str(instr), "PI_AUTH_JSON_PATH": str(auth)}


def uploads(calls):
    return [(src, tgt) for kind, src, tgt in calls if kind == "upload"]


def final_paths(calls):
    return [cmd for kind, user, cmd in calls if kind == "exec" and user is None]


def test_claude_gets_claude_md_in_its_config_dir(tmp_path, files):
    calls = run_setup(hpa.ClaudeCodeProfile, ClaudeCode, "anthropic/x", tmp_path, files)
    assert uploads(calls) == [(files["HARNESS_INSTRUCTIONS"], "/tmp/harbor-profile-CLAUDE.md")]
    assert '"/logs/agent/sessions/CLAUDE.md"' in final_paths(calls)[0]
    assert ("exec", "root", "set -o pipefail; chown agent /tmp/harbor-profile-CLAUDE.md") in calls


def test_codex_gets_agents_md_in_codex_home(tmp_path, files):
    calls = run_setup(hpa.CodexProfile, Codex, "openai/x", tmp_path, files)
    assert f'"{Codex._REMOTE_CODEX_HOME}/AGENTS.md"' in final_paths(calls)[0]


def test_pi_gets_login_and_agents_md(tmp_path, files):
    calls = run_setup(hpa.PiProfile, Pi, "openai-codex/x", tmp_path, files)
    assert [t for _, t in uploads(calls)] == ["/tmp/harbor-profile-auth.json", "/tmp/harbor-profile-AGENTS.md"]
    assert '"$HOME/.pi/agent/auth.json"' in final_paths(calls)[0]
    assert '"$HOME/.pi/agent/AGENTS.md"' in final_paths(calls)[1]


def test_symlinked_files_are_uploaded_as_their_real_file(tmp_path, files):
    # docker cp copies a symlink as a symlink. In the container, the link then points to a
    # path on the host that does not exist there. Thus the upload must use the real file.
    real_instr, real_auth = files["HARNESS_INSTRUCTIONS"], files["PI_AUTH_JSON_PATH"]
    (tmp_path / "link-AGENTS.md").symlink_to(real_instr)
    (tmp_path / "link-auth.json").symlink_to(real_auth)
    links = {
        "HARNESS_INSTRUCTIONS": str(tmp_path / "link-AGENTS.md"),
        "PI_AUTH_JSON_PATH": str(tmp_path / "link-auth.json"),
    }
    calls = run_setup(hpa.PiProfile, Pi, "openai-codex/x", tmp_path, links)
    sources = [src for src, _ in uploads(calls)]
    assert sources == [str(Path(real_auth).resolve()), str(Path(real_instr).resolve())]


def test_dangling_symlink_is_an_error(tmp_path):
    (tmp_path / "dangling.md").symlink_to(tmp_path / "nothing-here.md")
    with pytest.raises(RuntimeError, match="missing file"):
        extra_env = {"HARNESS_INSTRUCTIONS": str(tmp_path / "dangling.md")}
        run_setup(hpa.CodexProfile, Codex, "openai/x", tmp_path, extra_env)


def test_nothing_happens_without_variables(tmp_path):
    assert run_setup(hpa.CodexProfile, Codex, "openai/x", tmp_path, {}) == []


def test_missing_file_is_an_error(tmp_path):
    with pytest.raises(RuntimeError, match="missing file"):
        run_setup(hpa.PiProfile, Pi, "openai-codex/x", tmp_path, {"PI_AUTH_JSON_PATH": "/nope.json"})


def test_harbor_internals_that_we_use_exist():
    assert Codex._REMOTE_CODEX_HOME.as_posix() == "/tmp/codex-home"
    for cls in (ClaudeCode, Codex, Pi):
        for name in ("_get_env", "exec_as_root", "exec_as_agent", "setup"):
            assert hasattr(cls, name), f"{cls.__name__}.{name}"


# ---- real Harbor dry runs -----------------------------------------------------------------


@pytest.fixture
def local_task(tmp_path):
    t = tmp_path / "task"
    (t / "environment").mkdir(parents=True)
    (t / "tests").mkdir()
    (t / "instruction.md").write_text("Write hi to /app/hi.txt\n")
    (t / "environment/Dockerfile").write_text("FROM ubuntu:24.04\nWORKDIR /app\n")
    (t / "tests/test.sh").write_text("#!/bin/bash\necho 1 > /logs/verifier/reward.txt\n")
    (t / "task.toml").write_text('version = "1.0"\n[agent]\ntimeout_sec = 600\n[verifier]\ntimeout_sec = 60\n')
    return t


@pytest.fixture
def dry_env(tmp_path, files):
    stub = tmp_path / "stubbin"
    stub.mkdir()
    docker = stub / "docker"
    docker.write_text('#!/bin/sh\necho "Docker version 27.0.0"\n')  # Harbor checks that docker exists
    docker.chmod(0o755)
    e = dict(
        os.environ,
        PATH=f"{stub}{os.pathsep}{os.environ['PATH']}",
        PYTHONPATH=str(LIB),
        HOME=str(tmp_path),
        CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-test",
        CLAUDE_FORCE_OAUTH="1",
        CODEX_AUTH_JSON_PATH=files["PI_AUTH_JSON_PATH"],
        PI_AUTH_JSON_PATH=files["PI_AUTH_JSON_PATH"],
    )
    return e


@pytest.mark.skipif(shutil.which("harbor") is None, reason="harbor CLI not on PATH")
@pytest.mark.parametrize(
    "cls,model",
    [
        ("ClaudeCodeProfile", "anthropic/model-x"),
        ("CodexProfile", "openai/model-y"),
        ("PiProfile", "openai-codex/model-z"),
    ],
)
def test_harbor_accepts_the_agents(tmp_path, local_task, dry_env, files, cls, model):
    skills = tmp_path / "skills/s1"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("---\nname: s1\ndescription: test\n---\n")
    r = subprocess.run(
        [
            "harbor",
            "run",
            "-p",
            str(local_task),
            "-k",
            "1",
            "-e",
            "docker",
            "-y",
            "--dry-run",
            "-a",
            f"harbor_profile_agents:{cls}",
            "-m",
            model,
            "-o",
            str(tmp_path / "jobs"),
            "--skill",
            str(tmp_path / "skills"),
            "--ak",
            "version=1.0.0",
            "--ae",
            f"HARNESS_INSTRUCTIONS={files['HARNESS_INSTRUCTIONS']}",
        ],
        env=dry_env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "Dry run OK" in r.stdout + r.stderr, r.stdout + r.stderr
