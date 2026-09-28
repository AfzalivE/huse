import os
import shutil
import signal
import subprocess
import time

import pytest

from conftest import BIN, TEST_BASH, agents_target, huse


def profile(home, name):
    return home / ".harness" / "profiles" / name


@pytest.fixture
def ready(home, env):
    """huse is set up, with the profiles "tuned" (copy of system) and "lean" (empty)."""
    huse("setup", env=env, check=True)
    huse("new", "tuned", "--from", "system", env=env, check=True)
    huse("new", "lean", env=env, check=True)
    return env


def system_agents(home):
    return str(home / ".harness" / "agents.system")


# ---- help and errors ------------------------------------------------------------------


def test_help_lists_all_commands(env):
    r = huse("help", env=env)
    for cmd in ("setup", "new", "use", "off", "run", "ls", "status", "init"):
        assert f"huse {cmd}" in r.stderr


def test_unknown_command_fails(env):
    assert huse("bogus", env=env).returncode == 1


def test_use_and_run_need_setup(home, env):
    huse("new", "lean", env=env, check=True)
    for args in (("use", "lean"), ("run", "lean", "true")):
        r = huse(*args, env=env)
        assert r.returncode == 1
        assert "huse setup" in r.stderr
    assert (home / ".agents").is_dir() and not (home / ".agents").is_symlink()


# ---- setup ----------------------------------------------------------------------------


def test_setup_moves_real_folder_and_is_idempotent(home, env):
    r = huse("setup", env=env, check=True)
    assert "moved ~/.agents" in r.stdout
    assert agents_target(home) == system_agents(home)
    assert (home / ".agents/skills/orig/SKILL.md").exists()  # content still reachable
    again = huse("setup", env=env, check=True)
    assert "already set up" in again.stdout


def test_setup_keeps_dotfiles_symlink(home, env, tmp_path):
    dot = tmp_path / "dotfiles" / "agents"
    dot.parent.mkdir(parents=True)
    shutil.move(str(home / ".agents"), str(dot))
    (home / ".agents").symlink_to(dot)
    huse("setup", env=env, check=True)
    assert os.readlink(system_agents(home)) == str(dot.resolve())
    assert (home / ".agents/skills/orig/SKILL.md").exists()


def test_setup_without_agents_makes_empty_folder(home, env):
    shutil.rmtree(home / ".agents")
    huse("setup", env=env, check=True)
    assert os.path.isdir(system_agents(home))
    assert agents_target(home) == system_agents(home)


def test_setup_refuses_when_both_exist(home, env):
    (home / ".harness/agents.system").mkdir(parents=True)
    r = huse("setup", env=env)
    assert r.returncode == 1
    assert "Merge them by hand" in r.stderr
    assert (home / ".agents").is_dir() and not (home / ".agents").is_symlink()


# ---- new ------------------------------------------------------------------------------


def test_new_copies_config_but_not_logins_or_state(home, env):
    (home / ".codex/config.toml").write_text('model = "x"\n')
    (home / ".codex/auth.json").write_text("{}")
    (home / ".codex/sessions").mkdir()
    (home / ".claude/.credentials.json").write_text("{}")
    (home / ".claude/settings.json").write_text("{}")
    (home / ".claude/projects").mkdir()
    (home / ".pi/agent/auth.json").write_text("{}")
    huse("new", "p", "--from", "system", env=env, check=True)
    p = profile(home, "p")
    assert (p / "codex/config.toml").exists() and (p / "claude/settings.json").exists()
    for gone in ("codex/auth.json", "codex/sessions", "claude/.credentials.json", "claude/projects", "pi/auth.json"):
        assert not (p / gone).exists(), gone
    assert (p / "agents/skills/orig/SKILL.md").exists()


def test_new_empty_profile_has_all_parts(home, env):
    huse("new", "p", env=env, check=True)
    for part in ("claude", "codex", "pi", "agents"):
        assert (profile(home, "p") / part).is_dir()


@pytest.mark.parametrize("name", ["system", "off", "a/b", ".hidden"])
def test_new_rejects_reserved_and_bad_names(env, name):
    r = huse("new", name, env=env)
    assert r.returncode == 1 and "bad profile name" in r.stderr


def test_new_fails_if_exists_or_source_missing(env):
    huse("new", "p", env=env, check=True)
    assert "already exists" in huse("new", "p", env=env).stderr
    assert "no profile 'nope'" in huse("new", "q", "--from", "nope", env=env).stderr


# ---- use (new shell) ------------------------------------------------------------------


def test_use_opens_shell_and_restores_agents(home, ready):
    script = 'echo "P=$HARNESS_PROFILE C=$CODEX_HOME A=$(readlink ~/.agents)"; exit 3\n'
    r = huse("use", "tuned", env=ready, input=script)
    assert r.returncode == 3  # the exit code of the shell
    p = profile(home, "tuned")
    assert f"P=tuned C={p}/codex A={p}/agents" in r.stdout
    assert agents_target(home) == system_agents(home)


def test_use_in_a_huse_shell_is_refused(home, ready):
    r = huse("use", "tuned", env=ready, input="huse use lean; echo rc=$?; exit\n")
    assert "rc=1" in r.stdout
    assert "already a huse shell" in r.stderr


def test_restore_is_skipped_if_another_shell_changed_agents(home, ready):
    lean = profile(home, "lean") / "agents"
    r = huse("use", "tuned", env=ready, input=f'ln -sfn "{lean}" ~/.agents; exit\n')
    assert r.returncode == 0
    assert agents_target(home) == str(lean)


def test_use_unknown_profile(ready):
    r = huse("use", "nope", env=ready)
    assert r.returncode == 1 and "no profile 'nope'" in r.stderr


def test_hangup_restores_agents(home, ready):
    p = subprocess.Popen(
        [TEST_BASH, str(BIN / "huse"), "use", "lean"],
        env=ready,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    p.stdin.write("sleep 2; exit\n")
    p.stdin.flush()
    deadline = time.time() + 5
    while agents_target(home) == system_agents(home) and time.time() < deadline:
        time.sleep(0.05)
    assert agents_target(home).endswith("/lean/agents")
    p.send_signal(signal.SIGHUP)
    p.communicate(timeout=15)
    assert p.returncode == 129
    assert agents_target(home) == system_agents(home)


# ---- run --------------------------------------------------------------------------------


def test_run_switches_restores_and_keeps_exit_code(home, ready):
    r = huse("run", "lean", "sh", "-c", 'echo "$CODEX_HOME $(readlink "$HOME/.agents")"; exit 7', env=ready)
    assert r.returncode == 7
    p = profile(home, "lean")
    assert f"{p}/codex {p}/agents" in r.stdout
    assert agents_target(home) == system_agents(home)


def test_run_inside_huse_shell_restores_to_that_profile(home, ready):
    r = huse("use", "tuned", env=ready, input='huse run lean true; echo "A=$(readlink ~/.agents)"; exit\n')
    assert f"A={profile(home, 'tuned')}/agents" in r.stdout


def test_run_system_unsets_profile_variables(ready):
    e = dict(ready, CODEX_HOME="/x", CLAUDE_CONFIG_DIR="/y", HARNESS_PROFILE="tuned")
    r = huse("run", "system", "sh", "-c", 'echo "[${CODEX_HOME-unset}][${CLAUDE_CONFIG_DIR-unset}]"', env=e)
    assert "[unset][unset]" in r.stdout


# ---- shell integration ------------------------------------------------------------------


def test_env_prints_only_shell_code(home, ready):
    r = huse("__env", "tuned", env=ready, check=True)
    lines = r.stdout.splitlines()
    assert len(lines) == 1 and lines[0].startswith("export ")
    assert "huse:" in r.stderr
    # The path has a space. The quoting must survive eval.
    out = subprocess.run(["bash", "-c", r.stdout + 'printf "%s" "$CODEX_HOME"'], capture_output=True, text=True).stdout
    assert out == f"{profile(home, 'tuned')}/codex"


def test_env_error_prints_nothing_on_stdout(ready):
    r = huse("__env", "nope", env=ready)
    assert r.returncode == 1 and r.stdout == ""


def test_env_off_unsets_and_never_sets_defaults(ready):
    r = huse("__env", "off", env=ready, check=True)
    assert r.stdout.startswith("unset ")
    assert "CLAUDE_CONFIG_DIR" in r.stdout and "export" not in r.stdout


SHELLS = [s for s in ("bash", "zsh") if shutil.which(s)]


@pytest.mark.parametrize("shell", SHELLS)
def test_integration_changes_current_shell(home, ready, shell):
    script = (
        'eval "$(huse init)"; huse use tuned; echo "C=$CODEX_HOME A=$(readlink ~/.agents)"; '
        'huse off; echo "C=${CODEX_HOME:-unset} A=$(readlink ~/.agents)"'
    )
    r = subprocess.run([shell, "-c", script], env=ready, capture_output=True, text=True, timeout=30)
    p = profile(home, "tuned")
    assert f"C={p}/codex A={p}/agents" in r.stdout
    assert f"C=unset A={system_agents(home)}" in r.stdout


@pytest.mark.parametrize("shell", SHELLS)
def test_integration_bad_profile_changes_nothing(home, ready, shell):
    script = 'eval "$(huse init)"; huse use nope; echo "rc=$? C=${CODEX_HOME:-unset}"'
    r = subprocess.run([shell, "-c", script], env=ready, capture_output=True, text=True, timeout=30)
    assert "rc=1 C=unset" in r.stdout
    assert agents_target(home) == system_agents(home)


# ---- off, ls, status --------------------------------------------------------------------


def test_off_outside_huse_shell_resets_agents(home, ready):
    os.remove(home / ".agents")
    (home / ".agents").symlink_to(profile(home, "lean") / "agents")
    r = huse("off", env=dict(ready, HARNESS_PROFILE="lean"))
    assert r.returncode == 1 and "huse init" in r.stderr  # cannot change this shell
    assert agents_target(home) == system_agents(home)


def test_note_when_another_shell_had_agents(home, ready):
    os.remove(home / ".agents")
    (home / ".agents").symlink_to(profile(home, "lean") / "agents")
    r = huse("run", "tuned", "true", env=ready)
    assert "probably from another shell" in r.stderr


def test_ls_marks_shell_profile_and_agents_owner(home, ready):
    os.remove(home / ".agents")
    (home / ".agents").symlink_to(profile(home, "lean") / "agents")
    out = huse("ls", env=dict(ready, HARNESS_PROFILE="tuned"), check=True).stdout.splitlines()
    assert "  lean   (~/.agents)" in out
    assert "* tuned" in out


def test_status_notes_mismatch(home, ready):
    out = huse("status", env=dict(ready, HARNESS_PROFILE="tuned"), check=True).stdout
    assert "~/.agents profile:    system" in out
    assert "Another shell probably switched it" in out
