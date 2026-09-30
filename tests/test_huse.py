import os
import shutil
import subprocess

import pytest

from conftest import BIN, huse, seen

# The user's login shell. On macOS this is zsh. `huse use` opens it, and the integration runs in it.
SHELLS = [s for s in ("bash", "zsh") if shutil.which(s)]
HARNESSES = ("claude", "codex", "pi")


def profile(home, name):
    return home / ".harness" / "profiles" / name


def store(home):
    return home / ".harness" / "skills"


def add_to_store(home, name):
    d = store(home) / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
    return d


def system_part(home, harness):
    return home / {"claude": ".claude", "codex": ".codex", "pi": ".pi/agent"}[harness]


@pytest.fixture
def ready(home, env):
    """The profiles "tuned" (copy of system) and "lean" (empty)."""
    huse("new", "tuned", "--from", "system", env=env, check=True)
    huse("new", "lean", env=env, check=True)
    return env


# ---- help and errors ----------------------------------------------------------------


def test_help_lists_all_commands(env):
    r = huse("help", env=env)
    for cmd in ("new", "use", "off", "run", "ls", "status", "setup", "skill ls", "skill add", "skill rm", "init"):
        assert f"huse {cmd}" in r.stderr


def test_unknown_command_fails(env):
    assert huse("bogus", env=env).returncode == 1


# ---- new --------------------------------------------------------------------------------


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


def test_new_keeps_skill_links_as_links(home, env):
    add_to_store(home, "s1")
    huse("skill", "add", "system", "s1", "codex", env=env, check=True)
    huse("new", "p", "--from", "system", env=env, check=True)
    link = profile(home, "p") / "codex/skills/s1"
    assert link.is_symlink() and os.readlink(link) == str(store(home) / "s1")


def test_new_empty_profile_has_all_parts(home, env):
    huse("new", "p", env=env, check=True)
    assert sorted(x.name for x in profile(home, "p").iterdir()) == sorted(HARNESSES)


@pytest.mark.parametrize("name", ["system", "off", "a/b", ".hidden"])
def test_new_rejects_reserved_and_bad_names(env, name):
    r = huse("new", name, env=env)
    assert r.returncode == 1 and "bad profile name" in r.stderr


def test_new_fails_if_exists_or_source_missing(env):
    huse("new", "p", env=env, check=True)
    assert "already exists" in huse("new", "p", env=env).stderr
    assert "no profile 'nope'" in huse("new", "q", "--from", "nope", env=env).stderr


# ---- run -------------------------------------------------------------------------------------


def test_codex_and_pi_in_a_profile_get_the_profile_folders(home, ready):
    for tool in ("codex", "pi"):
        out = seen(huse("run", "tuned", tool, "-p", "hi", env=ready, check=True).stdout)
        assert out["TOOL"] == [tool]
        assert out["CODEX_HOME"] == [str(profile(home, "tuned") / "codex")]
        assert out["PI_DIR"] == [str(profile(home, "tuned") / "pi")]
        assert out["HOME"] == [str(home)]  # huse does not change HOME
        assert out["ARG"] == ["-p", "hi"]  # huse adds nothing


def test_run_sets_the_profile_and_keeps_exit_code(home, ready):
    r = huse("run", "lean", "sh", "-c", 'echo "$CLAUDE_CONFIG_DIR"; exit 7', env=ready)
    assert r.returncode == 7
    assert f"{profile(home, 'lean')}/claude" in r.stdout


def test_run_system_unsets_profile_variables(ready):
    e = dict(ready, CODEX_HOME="/x", CLAUDE_CONFIG_DIR="/y", PI_CODING_AGENT_DIR="/z", HARNESS_PROFILE="tuned")
    script = 'echo "[${CODEX_HOME-unset}][${CLAUDE_CONFIG_DIR-unset}][${PI_CODING_AGENT_DIR-unset}]"'
    r = huse("run", "system", "sh", "-c", script, env=e)
    assert "[unset][unset][unset]" in r.stdout


def test_two_profiles_do_not_mix(home, ready):
    a = seen(huse("run", "tuned", "codex", env=ready, check=True).stdout)
    b = seen(huse("run", "lean", "codex", env=ready, check=True).stdout)
    assert a["CODEX_HOME"] == [str(profile(home, "tuned") / "codex")]
    assert b["CODEX_HOME"] == [str(profile(home, "lean") / "codex")]


# ---- use (new shell) ------------------------------------------------------------------------


@pytest.mark.parametrize("shell", SHELLS)
def test_use_opens_a_shell_with_the_profile(home, ready, shell):
    script = 'echo "P=$HARNESS_PROFILE C=$CODEX_HOME H=$HOME"; exit 3\n'
    r = huse("use", "tuned", env=dict(ready, SHELL=shutil.which(shell)), input=script)
    assert r.returncode == 3  # the exit code of the shell
    assert f"P=tuned C={profile(home, 'tuned')}/codex H={home}" in r.stdout


@pytest.mark.parametrize("shell", SHELLS)
def test_use_in_a_huse_shell_is_refused(ready, shell):
    r = huse("use", "tuned", env=dict(ready, SHELL=shutil.which(shell)), input="huse use lean; echo rc=$?; exit\n")
    assert "rc=1" in r.stdout
    assert "already a huse shell" in r.stderr


def test_use_unknown_profile(ready):
    r = huse("use", "nope", env=ready)
    assert r.returncode == 1 and "no profile 'nope'" in r.stderr


# ---- shell integration ------------------------------------------------------------------------


def test_env_prints_only_shell_code(home, ready):
    r = huse("__env", "tuned", env=ready, check=True)
    lines = r.stdout.splitlines()
    assert len(lines) == 1 and lines[0].startswith("export ")
    assert "HOME=" not in r.stdout.replace("CODEX_HOME=", "")
    assert "huse:" in r.stderr
    # The path has a space. The quoting must survive eval.
    script = r.stdout + 'printf "%s|%s" "$CODEX_HOME" "$PI_CODING_AGENT_DIR"'
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True).stdout
    assert out == f"{profile(home, 'tuned')}/codex|{profile(home, 'tuned')}/pi"


def test_env_error_prints_nothing_on_stdout(ready):
    r = huse("__env", "nope", env=ready)
    assert r.returncode == 1 and r.stdout == ""


def test_env_off_unsets_and_never_sets_defaults(ready):
    r = huse("__env", "off", env=ready, check=True)
    assert r.stdout.startswith("unset ")
    assert "CLAUDE_CONFIG_DIR" in r.stdout and "export" not in r.stdout


@pytest.mark.parametrize("shell", SHELLS)
def test_integration_changes_the_current_shell(home, ready, shell):
    script = (
        'eval "$(huse init)"; huse use tuned; huse use lean; huse use tuned; '
        'echo "C=$CODEX_HOME H=$HOME"; '
        'huse off; echo "C=${CODEX_HOME:-unset} H=$HOME"'
    )
    r = subprocess.run([shell, "-c", script], env=ready, capture_output=True, text=True, timeout=30)
    assert f"C={profile(home, 'tuned')}/codex H={home}" in r.stdout
    assert f"C=unset H={home}" in r.stdout


@pytest.mark.parametrize("shell", SHELLS)
def test_integration_bad_profile_changes_nothing(ready, shell):
    script = 'eval "$(huse init)"; huse use nope; echo "rc=$? C=${CODEX_HOME:-unset}"'
    r = subprocess.run([shell, "-c", script], env=ready, capture_output=True, text=True, timeout=30)
    assert "rc=1 C=unset" in r.stdout


# ---- setup: move ~/.agents/skills to the store ----------------------------------------------


def test_setup_moves_global_skills_and_keeps_codex_and_pi_using_them(home, env):
    huse("setup", env=env, check=True)
    assert list((home / ".agents/skills").iterdir()) == []
    assert (store(home) / "orig/SKILL.md").exists()
    for h in ("codex", "pi"):
        assert os.readlink(system_part(home, h) / "skills/orig") == str(store(home) / "orig")
    assert not (home / ".claude/skills/orig").exists()  # Claude did not read ~/.agents before


def test_setup_follows_a_symlinked_agents_folder(home, env, tmp_path):
    dot = tmp_path / "dotfiles-agents"
    shutil.move(str(home / ".agents"), str(dot))
    (home / ".agents").symlink_to(dot)
    huse("setup", env=env, check=True)
    assert (store(home) / "orig/SKILL.md").exists()
    assert (home / ".agents").is_symlink()


def test_setup_makes_a_relative_skill_link_absolute(home, env, tmp_path):
    real = home / "my-skills/rel"
    real.mkdir(parents=True)
    (real / "SKILL.md").write_text("---\n")
    (home / ".agents/skills/rel").symlink_to("../../my-skills/rel")
    huse("setup", env=env, check=True)
    assert os.readlink(store(home) / "rel") == str(real.resolve())
    assert (store(home) / "rel/SKILL.md").exists()


def test_setup_never_overwrites_the_store(home, env):
    add_to_store(home, "orig")
    r = huse("setup", env=env, check=True)
    assert "already exists" in r.stderr
    assert (home / ".agents/skills/orig/SKILL.md").exists()


def test_setup_twice_is_harmless(home, env):
    huse("setup", env=env, check=True)
    assert "no skills to move" in huse("setup", env=env, check=True).stdout


# ---- skill ls, add, rm ------------------------------------------------------------------------


def test_skill_add_links_all_harnesses_by_default(home, ready):
    add_to_store(home, "s1")
    huse("skill", "add", "tuned", "s1", env=ready, check=True)
    for h in HARNESSES:
        assert os.readlink(profile(home, "tuned") / h / "skills/s1") == str(store(home) / "s1")
    assert not (profile(home, "lean") / "codex/skills/s1").exists()


def test_skill_add_and_rm_for_one_harness(home, ready):
    add_to_store(home, "s1")
    huse("skill", "add", "tuned", "s1", "codex", "pi", env=ready, check=True)
    assert not (profile(home, "tuned") / "claude/skills/s1").exists()
    huse("skill", "rm", "tuned", "s1", "pi", env=ready, check=True)
    assert (profile(home, "tuned") / "codex/skills/s1").is_symlink()
    assert not (profile(home, "tuned") / "pi/skills/s1").exists()
    assert (store(home) / "s1/SKILL.md").exists()  # rm never touches the store


def test_skill_add_and_rm_say_what_they_did(home, ready):
    add_to_store(home, "s1")
    r = huse("skill", "add", "tuned", "s1", "codex", "pi", env=ready, check=True)
    assert r.stdout == "huse: 'tuned' now uses s1 in: codex pi\n"
    r = huse("skill", "add", "tuned", "s1", env=ready, check=True)
    assert r.stdout == "huse: 'tuned' now uses s1 in: claude\nhuse: 'tuned' already used s1 in: codex pi\n"
    r = huse("skill", "rm", "tuned", "s1", "pi", env=ready, check=True)
    assert r.stdout == "huse: 'tuned' no longer uses s1 in: pi\n"
    r = huse("skill", "rm", "tuned", "s1", "pi", env=ready, check=True)
    assert r.stdout == "huse: 'tuned' did not use s1 in: pi\n"


def test_skill_ls_shows_where_a_profile_uses_each_skill(home, ready):
    add_to_store(home, "a")
    add_to_store(home, "b")
    huse("skill", "add", "tuned", "a", "codex", env=ready, check=True)
    assert huse("skill", "ls", "tuned", env=ready, check=True).stdout.splitlines() == ["a  (tuned: codex)", "b"]


def test_skill_ls_uses_the_profile_of_this_shell(home, ready):
    add_to_store(home, "a")
    huse("skill", "add", "lean", "a", "pi", env=ready, check=True)
    out = huse("skill", "ls", env=dict(ready, HARNESS_PROFILE="lean"), check=True).stdout
    assert out.splitlines() == ["a  (lean: pi)"]


def test_skill_rm_keeps_a_real_skill_folder(home, ready):
    real = profile(home, "tuned") / "codex/skills/mine"
    real.mkdir(parents=True)
    r = huse("skill", "rm", "tuned", "mine", "codex", env=ready, check=True)
    assert "not a link to the store" in r.stderr and real.is_dir()


def test_skill_add_keeps_an_existing_folder(home, ready):
    add_to_store(home, "s1")
    real = profile(home, "tuned") / "codex/skills/s1"
    real.mkdir(parents=True)
    r = huse("skill", "add", "tuned", "s1", "codex", env=ready, check=True)
    assert "not a link to the store" in r.stderr and not real.is_symlink()


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (("add", "tuned", "nope"), "no skill 'nope'"),
        (("add", "nope", "s1"), "no profile 'nope'"),
        (("add", "tuned", "s1", "cursor"), "harness must be"),
        (("add", "tuned", "../x"), "bad skill name"),
        (("add", "tuned"), "give a profile and a skill"),
        (("bogus",), "usage"),
    ],
)
def test_skill_errors(home, ready, args, error):
    add_to_store(home, "s1")
    r = huse("skill", *args, env=ready)
    assert r.returncode == 1 and error in r.stderr


def test_skill_add_for_system(home, env):
    add_to_store(home, "s1")
    huse("skill", "add", "system", "s1", "claude", env=env, check=True)
    assert os.readlink(home / ".claude/skills/s1") == str(store(home) / "s1")


# ---- off, ls, status ---------------------------------------------------------------------------


def test_off_outside_huse_shell_with_a_profile(ready):
    r = huse("off", env=dict(ready, HARNESS_PROFILE="lean"))
    assert r.returncode == 1 and "huse init" in r.stderr


def test_ls_marks_the_profile_of_this_shell(ready):
    out = huse("ls", env=dict(ready, HARNESS_PROFILE="tuned"), check=True).stdout.splitlines()
    assert out == ["  lean", "* tuned"]


def test_status_shows_the_profile(home, ready):
    e = dict(ready, HARNESS_PROFILE="tuned", CODEX_HOME=str(profile(home, "tuned") / "codex"))
    out = huse("status", env=e, check=True).stdout
    assert "shell profile:        tuned" in out
    assert f"CODEX_HOME          = {profile(home, 'tuned')}/codex" in out


def test_status_warns_about_skills_in_the_global_folder(home, ready):
    out = huse("status", env=ready, check=True).stdout
    assert "WARNING: ~/.agents/skills has 1 skills" in out and "huse setup" in out
    huse("setup", env=ready, check=True)
    assert "WARNING" not in huse("status", env=ready, check=True).stdout


def test_huse_works_through_a_symlink(home, ready, tmp_path):
    link = tmp_path / "linkbin"
    link.mkdir()
    (link / "huse").symlink_to(BIN / "huse")
    e = dict(ready, PATH=str(link) + os.pathsep + ready["PATH"])
    r = subprocess.run(["huse", "__env", "tuned"], env=e, capture_output=True, text=True)
    assert "CODEX_HOME=" in r.stdout and r.returncode == 0


# ---- promote -------------------------------------------------------------------------------


@pytest.fixture
def main_setup(home):
    """A normal setup with config, a login, and sessions."""
    (home / ".codex/config.toml").write_text('model = "old"\n')
    (home / ".codex/hooks.json").write_text("{}")
    (home / ".codex/auth.json").write_text('{"main": 1}')
    (home / ".codex/sessions").mkdir()
    (home / ".codex/sessions/s.jsonl").write_text("x")
    (home / ".codex/session_index.jsonl").write_text("x")
    (home / ".claude/settings.json").write_text('{"old": 1}')
    (home / ".pi/agent/settings.json").write_text('{"old": 1}')
    return home


def test_promote_makes_the_profile_the_main_setup(home, env, main_setup):
    huse("new", "tuned", env=env, check=True)
    (profile(home, "tuned") / "codex/config.toml").write_text('model = "new"\n')
    (profile(home, "tuned") / "codex/auth.json").write_text('{"profile": 1}')
    (profile(home, "tuned") / "claude/CLAUDE.md").write_text("# new\n")
    r = huse("promote", "tuned", env=env, check=True)
    assert "before-tuned" in r.stdout
    assert (home / ".codex/config.toml").read_text() == 'model = "new"\n'
    assert not (home / ".codex/hooks.json").exists()  # main now matches the profile
    assert not (home / ".claude/settings.json").exists()
    assert (home / ".claude/CLAUDE.md").read_text() == "# new\n"
    # Logins, sessions, and state never move.
    assert (home / ".codex/auth.json").read_text() == '{"main": 1}'
    assert (home / ".codex/sessions/s.jsonl").exists() and (home / ".codex/session_index.jsonl").exists()
    # The profile does not change.
    assert (profile(home, "tuned") / "codex/config.toml").exists()


def test_promote_saves_the_old_main_setup_as_a_profile(home, env, main_setup):
    huse("new", "tuned", env=env, check=True)
    huse("promote", "tuned", env=env, check=True)
    saved = profile(home, "before-tuned")
    assert (saved / "codex/config.toml").read_text() == 'model = "old"\n'
    assert (saved / "codex/hooks.json").exists() and (saved / "claude/settings.json").exists()
    for gone in ("codex/auth.json", "codex/sessions", "codex/session_index.jsonl"):
        assert not (saved / gone).exists(), gone


def test_promote_the_saved_profile_to_go_back(home, env, main_setup):
    huse("new", "tuned", env=env, check=True)
    huse("promote", "tuned", env=env, check=True)
    r = huse("promote", "before-tuned", env=env, check=True)
    assert "before-before-tuned" in r.stdout
    assert (home / ".codex/config.toml").read_text() == 'model = "old"\n'
    assert (home / ".codex/hooks.json").exists()
    assert (home / ".claude/settings.json").read_text() == '{"old": 1}'


def test_promote_numbers_the_saved_name_and_accepts_save_as(home, env, main_setup):
    huse("new", "tuned", env=env, check=True)
    huse("new", "before-tuned", env=env, check=True)
    assert "before-tuned-2" in huse("promote", "tuned", env=env, check=True).stdout
    huse("promote", "tuned", "--save-as", "old-main", env=env, check=True)
    assert profile(home, "old-main").is_dir()


def test_promote_keeps_skill_links_and_links_to_dotfiles(home, env, main_setup, tmp_path):
    dot = tmp_path / "dotfiles-settings.json"
    dot.write_text("{}")
    (home / ".pi/agent/settings.json").unlink()
    (home / ".pi/agent/settings.json").symlink_to(dot)
    add_to_store(home, "s1")
    huse("new", "tuned", env=env, check=True)
    huse("skill", "add", "tuned", "s1", "codex", env=env, check=True)
    huse("promote", "tuned", env=env, check=True)
    assert os.readlink(home / ".codex/skills/s1") == str(store(home) / "s1")
    assert os.readlink(profile(home, "before-tuned") / "pi/settings.json") == str(dot)
    assert dot.read_text() == "{}"


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (("nope",), "no profile 'nope'"),
        (("system",), "give a profile"),
        (("tuned", "--save-as", "tuned"), "already exists"),
        (("tuned", "--save-as", "a/b"), "bad profile name"),
        ((), "give a profile"),
    ],
)
def test_promote_errors_change_nothing(home, env, main_setup, args, error):
    huse("new", "tuned", env=env, check=True)
    r = huse("promote", *args, env=env)
    assert r.returncode == 1 and error in r.stderr
    assert (home / ".codex/config.toml").read_text() == 'model = "old"\n'
