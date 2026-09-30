# Handoff: harness-tools

This file gives a new agent (for example Claude Code) what it needs to continue this project: the current state, the design decisions and their reasons, the known limits, and the open work.

Read these files first. They are the source of truth:

- `AGENTS.md`: rules, invariants, conventions, and how to test. Obey it.
- `README.md`: the repo, the folders, and all `huse` docs.
- `docs/heval.md`: all `heval` docs.

When the open work in this file is done, delete this file, or move the parts that stay true into `AGENTS.md`.

## What the project is

Two command-line tools for agent harness profiles (Claude Code, Codex, pi):

- `bin/huse` (Bash): makes profiles and uses them one shell at a time.
- `bin/heval` (Bash wrapper around Harbor, with Python in `lib/`): runs Harbor benchmark suites against profiles with the user's CLI subscription logins, and compares two profiles paired per task.

## Current state

- Version 0.1.0, not released. `CHANGELOG.md` has one section.
- `make check` passes: shellcheck, ruff, and 133 tests (Harbor tests skip without harbor).
- Tested with:
  - Bash 3.2.57 (built from Apple's source, `apple-oss-distributions/bash`) and bash 5, zsh.
  - The real Codex CLI 0.158.0 and pi 0.87.1 (`tests/test_agents_real.py`). No model and no login.
  - Harbor 0.23.0 (`tests/test_harbor.py`, including real `harbor run --dry-run`).
- **CI never ran.** `.github/workflows/ci.yml` was written but not run on GitHub. Check the first run of each job: `lint`, `test` (Ubuntu and macOS, with Bash 3.2 on macOS), `harbor`, and `agents`.
- The user may not have a git repo or a first commit yet. Check with `git status`.

## The user's setup

These are facts from the conversation. Confirm them with the user before you depend on them.

- **Machine:** macOS. Login shell zsh. The repo is probably at `~/code/harness-tools`, with `bin/` on `PATH`.
- **Old `~/.agents` layout:** the user ran `huse setup` from an older version. Thus, `~/.agents` is a symlink to `~/.harness/agents.system`. The new `huse setup` follows that link and moves the skills from there. `heval` no longer reads `agents.system`.
- **heval data:** it is in `~/.heval` (`eval.env`, `logins/codex`, `logins/pi`, `jobs/`). Older heval files in `~/.harness` make `heval` print a note.
- **pi:** the user runs pi with the `openai-codex` provider (ChatGPT subscription). The first `heval run pi system` failed with "No API key found for openai-codex", because `PI_AUTH_JSON_PATH` was not set. The login check in `heval run` now catches this. The user may still need to:
  - make the eval login (`PI_CODING_AGENT_DIR=~/.heval/logins/pi pi`, then `/login`),
  - set `PI_AUTH_JSON_PATH` in `~/.heval/eval.env`,
  - delete the failed job `~/.heval/jobs/terminal-bench-terminal-bench-4.0.0__pi__system__20260928-025636`, if it is still there.
- **Suite:** `eval.conf` uses `terminal-bench/terminal-bench@4.0.0` (66 tasks, 8-hour agent timeout). The model and version lines in the repo's `eval.conf` are still placeholders. The user's local copy may have values.

## Design decisions (do not undo them without asking the user)

### The main goal (confirmed by the user on 2026-09-30)

Try a new harness setup from scratch in one shell, keep the main setup in all other shells, and make the new setup the main one when it is ready (`huse promote`). `heval` is a side effect. Sessions are per profile on purpose: a profile from scratch has its own sessions. The user rejected designs that link or sync sessions between profiles (a sync problem).

### huse: CODEX_HOME and a central skill store (changed on 2026-09-30)

A profile sets only `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `PI_CODING_AGENT_DIR`. Skills are kept one time in `~/.harness/skills`. Each harness folder of a profile has links to the skills that it uses (`huse skill add|rm`). `huse setup` moves `~/.agents/skills` to the store, because Codex and pi read that folder in every profile. `huse status` warns when it has skills again.

The user rejected the earlier design, in which `HOME` was a profile home with its own `.agents` link. A backup of that version is not in the repo.

Known costs, accepted by the user:

- Codex marks `$CODEX_HOME/skills` as deprecated (`codex-rs/ext/skills/src/host_roots.rs`, PR #10437). It still works in Codex 0.159.0. `tests/test_agents_real.py` is the early warning.
- `npx skills add -g` always installs into `homedir()/.agents/skills`; Codex and pi count as "universal" agents there. There is no setting to change it. The user said to deal with `npx skills` later. A `HOME=<store parent>` wrapper works if it also sets `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `npm_config_userconfig`, `npm_config_cache`, `GIT_CONFIG_GLOBAL`, and `GH_CONFIG_DIR` (tested with skills 1.7.0, except git and gh).

Rejected designs, and why:

| Design | Why it was rejected |
| --- | --- |
| `HOME` is a profile home | The user did not like it: the whole shell sees another `HOME`. |
| Switch the global `~/.agents` symlink | It changes all shells. |
| Shims for `codex` and `pi` in `PATH` | Other tools (mise, asdf, Volta) also put shims first in `PATH`. |
| Add-only (keep `~/.agents/skills`) | A profile cannot hide a global skill. |

Other huse decisions:

- **No copies of logins.** Subscription logins rotate their refresh tokens. A copied `auth.json` breaks one of the two logins ("refresh token was already used").
- **Shell integration is optional.** Without it, `huse use` opens a new shell. A program cannot change its parent shell.

### heval

- **Harbor with CLI logins, not API keys:** a Claude Code token from `claude setup-token`, and separate Codex and pi eval logins in `~/.heval/logins`. The login check in `heval run` stops before a job without a login.
- **`lib/harbor_profile_agents.py`** subclasses Harbor's agents to upload the global instruction file and the pi login. It uploads the real file behind a symlink, because Harbor uploads with `docker cp`, which copies symlinks as symlinks. `AGENTS.md` lists the Harbor internals that this code uses.
- **Statistics:** per-task mean reward, bootstrap confidence intervals, and a paired difference. Usage-limit and infrastructure errors do not count, and `heval resume` runs them again. Never run real agent failures again.
- **Data folder:** `~/.heval`, apart from the huse profiles.

## Known limits

- **Apps that do not start from a shell** (desktop apps, IDE extensions) always use the normal setup.
- **`heval` sends only part of a profile:** skills, one global instruction file, and an optional `eval-settings.json` or `eval-config.toml`. It does not send hooks, plugins, MCP servers, or pi extensions. It warns about `@` imports but does not resolve them.
- **`heval compare` excludes only known login messages** ("No API key found", "refresh token was already used", `token_invalidated`), and only when the trial has an error. Other login messages count as normal failures.
- **Harbor resolves top-level skill folders, but not symlinks inside a skill.**

## Open work

In order of priority:

1. **Verify on the user's Mac, in a real terminal.** Run `huse setup`, then check `huse use`, `huse init` integration, and `huse skill add`. Check that `claude`, `codex`, and `pi` all see the right skills in a profile shell. Claude Code reading `CLAUDE_CONFIG_DIR/skills` links was not tested with the real program.
2. **Check the first CI run** and fix what fails.
3. Done: `heval compare` excludes login errors in the middle of a run (`LOGIN_RE` in `lib/harbor_compare.py`).
4. Done: `heval check` prints the tasks that failed the oracle run (`--oracle-failures`).
5. **Decisions that the user has not made yet.** Ask before you build:
   - Send pi extensions (the profile's `pi/` folder) into the containers, or mount host folders (for example an Obsidian vault). The user asked which option is which, and did not choose.
   - Resolve simple `@` imports in `CLAUDE.md` into one instruction file for `heval`.
   - A license for the repo.
   - A feature request to Codex for a config key for extra skill folders. It was offered as a draft, and not written.

## How to verify a change

```sh
make check          # shellcheck, ruff, all tests (Harbor and real-agent tests skip if not installed)
make test-agents    # needs: npm install -g @openai/codex @earendil-works/pi-coding-agent
make test-harbor    # needs: pip install "harbor==0.23.0"
make test-bash32    # macOS: the tests with /bin/bash (Bash 3.2)
```

## How to work with the user

- **Writing:** write all prose for the user, and all docs, in ASD-STE100 Simplified Technical English: short, direct sentences and active voice. Keep code, identifiers, and quotations exact.
- **Big design changes:** propose the design with its costs first, and wait for a "yes". The user decided each design step in this project, and rejected designs that are fragile.
- **Docs:** do not add migration steps for setups that the user never used. Keep `README.md` (huse) and `docs/heval.md` (heval) separate, with links between them.
- **Evidence:** the user asks for sources, for example links to the exact code. Give permalinks to a commit.
- **Proof:** say what you tested and what you did not test.
