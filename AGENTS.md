# AGENTS.md

Instructions for coding agents that work on this repo.

## What this repo is

Two command-line tools for agent harness profiles (Claude Code, Codex, pi):

- `bin/huse`: makes and switches profiles on the local machine. Bash.
- `bin/heval`: runs Harbor benchmark suites against profiles and compares them. Bash wrapper around Harbor and the Python files in `lib/`.

The repo holds code, settings, and docs only. User data is never in the repo: `huse` data is in `$HARNESS_ROOT` (default `~/.harness`), and `heval` data is in `$HEVAL_HOME` (default `~/.heval`).

## Layout

The layout of `$HARNESS_ROOT` is in the "Folders" section of `README.md`. The layout of `$HEVAL_HOME` is in the "Files" section of `docs/heval.md`. Keep them up to date when you add or move files there.

| Path | Purpose |
| --- | --- |
| `bin/huse` | Profile tool. Also prints the shell integration (`huse init`). |
| `bin/heval` | Eval tool. Reads `eval.conf`, loads `$HEVAL_HOME/eval.env`, reads profiles from `$HARNESS_ROOT`, calls `harbor`. |
| `lib/harbor_profile_agents.py` | Harbor agent subclasses. They upload global instructions and the pi login into the container. |
| `lib/harbor_compare.py` | Paired comparison of Harbor jobs. Also moves not-counted trials out for `harbor jobs resume`. |
| `eval.conf` | Suite, models, versions. Committed on purpose: it records how results were made. |
| `eval.env.example` | Template for the login file. The real file is `$HEVAL_HOME/eval.env`. |
| `tests/` | pytest tests for both tools. See "Tests". |
| `Makefile` | `make check` (lint and tests), `make test`, `make lint`, `make format`, `make test-harbor`, `make test-bash32`. |
| `pyproject.toml` | Version, dev tools (dependency groups `dev` and `harbor`), pytest and ruff settings. Not a Python package. |
| `.github/workflows/ci.yml` | CI: lint, tests on Linux and macOS (also with Bash 3.2), Harbor tests. |
| `CHANGELOG.md` | One section for each version. |
| `CLAUDE.md` | Makes Claude Code load this file. |
| `README.md` | Repo overview, install, and all `huse` docs. |
| `docs/heval.md` | All `heval` docs. |

## Safety rules for tests

- **Never run `huse` against the real home folder.** It makes profiles and the skill store there, and `huse setup` moves skills out of `~/.agents/skills`. Always set `HOME` to a temporary folder first. `HARNESS_ROOT` follows `HOME` by default.
- Do not run real agents, real Harbor jobs, or `harbor run` without `--dry-run`. They cost money and use the user's plan limits.
- Do not read, print, or copy `eval.env`, `auth.json`, `.credentials.json`, or tokens.
- Tests with the real `codex` and `pi` must never send a prompt. Use only requests that need no model, for example `skills/list` (Codex app server) and `get_commands` or `bash` (pi RPC).

## Invariants

Keep these true in every change.

### huse

1. `huse off` and `huse run system` must **unset** `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `PI_CODING_AGENT_DIR`. Do not set them to the default folders. Claude Code keeps `~/.claude.json` outside `~/.claude` only when `CLAUDE_CONFIG_DIR` is unset.
2. `huse new --from` must not copy login files (`auth.json`, `.credentials.json`). Subscription logins rotate their refresh tokens, so a copy breaks one of the two logins. It must also skip sessions, history, logs, and caches (see the `case` list in `_huse_new`).
3. A program cannot change its parent shell. Without integration, `huse use` opens a new shell. With integration, the function from `huse init` evaluates the output of `huse __env`.
4. The stdout of `huse __env` is evaluated by the user's shell. It must contain only shell code. Send all messages to stderr. On error, print nothing to stdout and exit non-zero.
5. The output of `huse init` must work in both bash and zsh.
6. A profile changes only the shell that uses it, through `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `PI_CODING_AGENT_DIR`. `huse` does not change `HOME`.
7. No shims and no `PATH` changes. Other tools (mise, asdf, Volta) also put shims in `PATH`, so a design that depends on `PATH` order breaks.
8. Skills: each skill is kept one time, in the store `$HARNESS_ROOT/skills`. A profile uses a skill through a link `<harness folder>/skills/<skill>` to the absolute store path. `huse skill rm` removes only such links. It never deletes a real folder or a store entry.
9. Only `huse setup` changes `~/.agents/skills`. It moves each entry to the store and never deletes a skill. It keeps an entry if the store already has that name. It makes a relative link absolute before it moves it. It links each moved skill into the normal setup of Codex and pi (`~/.codex/skills`, `~/.pi/agent/skills`), because they read `~/.agents/skills` before.
10. Codex reads `$CODEX_HOME/skills` (deprecated in Codex, but it works), and pi reads `$PI_CODING_AGENT_DIR/skills`. Both also read `~/.agents/skills` in every profile. `tests/test_agents_real.py` checks this with the real programs.
11. `huse promote` moves only the config entries in `_huse_config_entries`. It never moves or copies logins, sessions, history, state, or caches. It moves the old main config into a new profile before it copies, so that another promote goes back. It never deletes a file.
12. Profile names `system` and `off` are reserved. Names must not contain `/` or start with `.`.

### heval

1. `heval` only reads `$HARNESS_ROOT`. It writes only in `$HEVAL_HOME` (and in the containers).
2. `heval compare` finds jobs by folder name: `<suite>__<harness>__<profile>__<timestamp>`. If you change the name format, change `job_dirs` in `bin/heval` too.
3. A trial counts only when the verifier gave a reward. Usage limits, rate limits, API errors, auth errors, and setup errors do not count as failures. Exclude them, and let `heval resume` run them again.
4. Never run genuine agent failures again (for example, a real non-zero exit or a timeout with a reward). That biases the score upward.
5. `heval run` checks the login of the harness before the job starts, and `PiProfile` fails its setup without a login. A missing login must stop the run or make the trial an error. It must never become a graded failure.
6. Secrets go to Harbor through the host environment (`eval.env`) or through variable names that Harbor treats as sensitive. Do not put secret values in `--ae` or in job YAML.

## Harbor coupling

`lib/harbor_profile_agents.py` and `lib/harbor_compare.py` depend on Harbor internals. They were written against **Harbor 0.23.0**. After a Harbor upgrade, check these again:

- The classes `ClaudeCode`, `Codex`, and `Pi` in `harbor.agents.installed`.
- `self._get_env`, `self.exec_as_root`, `self.exec_as_agent`, `environment.upload_file`, and `environment.default_user`.
- Claude Code runs with `CLAUDE_CONFIG_DIR = <environment_logs_dir>/sessions`.
- Codex uses `Codex._REMOTE_CODEX_HOME` as `CODEX_HOME`.
- The auth variables `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_FORCE_OAUTH`, and `CODEX_AUTH_JSON_PATH`.
- The trial `result.json` fields: `task_name`, `verifier_result.rewards`, `exception_info`, `agent_result`, `agent_execution`, `agent_info`, `step_results`.
- The resume command: `harbor jobs resume -p <job>`.
- Uploads: the Docker environment uploads with `docker cp`, which copies a symlink as a symlink. Resolve symlinks before an upload (`Path.resolve()`). Harbor resolves top-level skill folders itself, but not symlinks inside a skill.

To read the installed source: `python3 -c "import harbor, os; print(os.path.dirname(harbor.__file__))"`.

## Code conventions

- **Bash 3.2 compatible.** macOS ships Bash 3.2. Do not use associative arrays, `mapfile`, `${var,,}`, or `readlink -f`. Under `set -u`, expand arrays that can be empty as `${a[@]+"${a[@]}"}`.
- **Backslashes:** do not rely on backslashes in `${var//x/y}` replacements. Their meaning changed between bash versions. Use `sed`.
- **Portable tools.** The code must work with BSD and GNU tools. Do not use `sed -i` in the scripts. `find -mindepth/-maxdepth`, `cp -a`, and `ln -sfn` are safe.
- **Messages.** Start each message with `huse:` or `heval:`. Send errors and notes to stderr.
- **Quoting.** Quote all paths. Home folders can contain spaces.
- **Python.** Standard library only in `lib/`, except Harbor itself.

## Tests

Run `make check` before you finish a change. It runs shellcheck, ruff, and pytest. Install the tools with `pip install --group dev` (pip 25.1 or later) or `uv sync --group dev`.

| File | What it tests |
| --- | --- |
| `tests/conftest.py` | Fixtures. Each test gets a temporary `HOME` with a space in its path, and a fake `harbor` that records its arguments and environment. `huse()` and `heval()` run the scripts with `$TEST_BASH`. |
| `tests/test_huse.py` | `huse` through its CLI: setup, new, use (new shell and integration, bash and zsh), run, off, ls, status, signals. |
| `tests/test_heval.py` | `heval` through its CLI: config checks, the Harbor command it builds, the login file, jobs, resume, compare. |
| `tests/test_harbor_compare.py` | Unit tests for `lib/harbor_compare.py`: which trials count, statistics, verdicts, prune. |
| `tests/test_harbor.py` | Marker `harbor`. The agent subclasses, and real Harbor dry runs with a stub `docker`. Skips if harbor is not installed. |
| `tests/test_agents_real.py` | Marker `agents`. The real `codex` and `pi` read the profile's skills through `CODEX_HOME` and `PI_CODING_AGENT_DIR`, and `~/.agents/skills` before and after `huse setup`. No model and no login. Skips if they are not installed. |
| `tests/test_repo.py` | Versions, help texts, and command tables in the docs stay in sync. |

Rules:

- Add or change a test for each change in behavior. For a bug fix, first write a test that fails.
- Tests must never use the real home folder. Use the `home` and `env` fixtures.
- Test the scripts through their CLI, the way a user runs them. Do not source them.
- **Shells:** the scripts are bash scripts, so they run with bash even when the user's login shell is zsh (the macOS default). The user's shell matters in two places: the new shell of `huse use` (`$SHELL`) and the `huse init` function. Test them with bash and zsh (`SHELLS` in `tests/test_huse.py`).
- **Bash 3.2:** `make test-bash32` runs all tests with `/bin/bash` on macOS, and CI runs it. On Linux, build Bash 3.2 from Apple's source (`apple-oss-distributions/bash` on GitHub) and run `make test-bash32 BASH32=/path/to/bash`.
- **Real programs:** `make test-agents` runs the tests with the real `codex` and `pi`. The CI job `agents` installs their newest versions, so a change in how they find skills shows up there.
- **Fake programs in tests:** use `printf`, not `echo`. `echo` in `dash` changes backslashes.
- **Harbor:** after a Harbor upgrade, run `make test-harbor` with the new version before you change the pin in `pyproject.toml` and in the CI workflow.
- **Versions:** to change the version, update `pyproject.toml`, `HUSE_VERSION` in `bin/huse`, `HEVAL_VERSION` in `bin/heval`, and `CHANGELOG.md`. `tests/test_repo.py` checks this.

## Docs

- `README.md` documents the repo and `huse`. `docs/heval.md` documents `heval`. Keep them separate. Link between them.
- When you change a command, update the command table in the docs, `huse help` (the text in `_huse_help`), and the usage header at the top of `bin/heval`. `tests/test_repo.py` checks that they list the same commands.
- Write the docs in ASD-STE100 Simplified Technical English: short sentences, active voice, one instruction per sentence.
- Use `<profile>` for a profile name in command syntax. The examples use the profile names `tuned` and `lean` (huse docs) and `base` and `skills-v2` (heval docs). Say that they are examples.
