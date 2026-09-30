"""Tests with the real Codex and pi programs. They skip when a program is not installed.

They check what huse depends on: Codex reads skills from $CODEX_HOME/skills (deprecated
in Codex, but it works), and pi reads them from $PI_CODING_AGENT_DIR/skills. Both follow
links into the store. Both also read ~/.agents/skills, which `huse setup` empties.
No model is called and no login is needed. Run them with:  pytest -m agents
CI installs the newest versions, so a change in Codex or pi shows up there.
"""

import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

from conftest import BIN, PROFILE_VARS

pytestmark = pytest.mark.agents

# Asks `codex app-server` (JSON-RPC over stdio) for the user skills that it finds.
CODEX_SKILLS = textwrap.dedent("""
    import json, subprocess, sys
    p = subprocess.Popen(["codex", "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True)
    def send(o):
        p.stdin.write(json.dumps(o) + "\\n"); p.stdin.flush()
    def recv(i):
        for line in p.stdout:
            m = json.loads(line)
            if m.get("id") == i:
                return m
    send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "huse-test", "version": "0"}}})
    recv(1)
    send({"method": "initialized"})
    send({"id": 2, "method": "skills/list", "params": {"cwds": [sys.argv[1]], "forceReload": True}})
    r = recv(2)
    p.kill()
    print(json.dumps(sorted({s["name"] for e in r["result"]["data"] for s in e["skills"]
                             if s.get("scope") == "user"})))
""")


@pytest.fixture
def real_env(home, tmp_path):
    """Like `env`, but with the real codex and pi on PATH, not the fakes.
    ~/.agents/skills has "orig". The store has "tuned-skill", and the profile "tuned" uses it."""
    e = {k: v for k, v in os.environ.items() if k not in PROFILE_VARS}
    e.update(HOME=str(home), PATH=f"{BIN}{os.pathsep}{os.environ['PATH']}", PI_OFFLINE="1", PI_SKIP_VERSION_CHECK="1")
    (home / ".agents/skills/orig/SKILL.md").write_text("---\nname: orig\ndescription: A test skill.\n---\nbody\n")
    skill = home / ".harness/skills/tuned-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: tuned-skill\ndescription: A test skill.\n---\nbody\n")
    for args in (("new", "tuned"), ("skill", "add", "tuned", "tuned-skill")):
        subprocess.run([str(BIN / "huse"), *args], env=e, check=True, capture_output=True)
    return e


def setup(env):
    subprocess.run([str(BIN / "huse"), "setup"], env=env, check=True, capture_output=True)


def need(tool):
    if shutil.which(tool) is None:
        pytest.skip(f"{tool} is not installed")


def pi_rpc(env, request, *prefix, cwd, program="pi"):
    """Send one RPC request to pi and return its response. Keep stdin open until the answer.
    program=None: the last element of prefix is the program."""
    p = subprocess.Popen(
        [*prefix, *([program] if program else []), "--mode", "rpc"],
        env=env,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        p.stdin.write(json.dumps(request) + "\n")
        p.stdin.flush()
        for line in p.stdout:
            if line.startswith("{"):
                msg = json.loads(line)
                if msg.get("type") == "response" and msg.get("command") == request["type"]:
                    return msg
        raise AssertionError(f"pi gave no response to {request}")
    finally:
        p.kill()
        p.wait(timeout=10)


def pi_skills(env, *prefix, cwd, program="pi"):
    msg = pi_rpc(env, {"type": "get_commands"}, *prefix, cwd=cwd, program=program)
    return sorted(c["name"] for c in msg["data"]["commands"] if c.get("source") == "skill")


def codex_skills(env, *prefix, cwd):
    r = subprocess.run(
        [*prefix, sys.executable, "-c", CODEX_SKILLS, str(cwd)],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


HUSE_RUN = (str(BIN / "huse"), "run", "tuned")


def test_pi_reads_the_profile_skills(real_env, tmp_path):
    need("pi")
    assert pi_skills(real_env, cwd=tmp_path) == ["skill:orig"]
    assert pi_skills(real_env, *HUSE_RUN, cwd=tmp_path) == ["skill:orig", "skill:tuned-skill"]
    setup(real_env)  # after this, ~/.agents/skills is empty
    assert pi_skills(real_env, cwd=tmp_path) == ["skill:orig"]
    assert pi_skills(real_env, *HUSE_RUN, cwd=tmp_path) == ["skill:tuned-skill"]


def test_codex_reads_the_profile_skills(real_env, tmp_path):
    need("codex")
    assert codex_skills(real_env, cwd=tmp_path) == ["orig"]
    assert codex_skills(real_env, *HUSE_RUN, cwd=tmp_path) == ["orig", "tuned-skill"]
    setup(real_env)
    assert codex_skills(real_env, cwd=tmp_path) == ["orig"]
    assert codex_skills(real_env, *HUSE_RUN, cwd=tmp_path) == ["tuned-skill"]


def test_an_absolute_path_reads_the_profile_skills(real_env, tmp_path):
    # No PATH lookup: the profile works through the environment alone.
    need("pi")
    setup(real_env)
    assert pi_skills(real_env, *HUSE_RUN, shutil.which("pi"), cwd=tmp_path, program=None) == ["skill:tuned-skill"]
