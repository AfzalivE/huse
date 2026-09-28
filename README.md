# harness-tools

Two tools for agent harness profiles (Claude Code, Codex, pi):

- `huse` switches between harness profiles on your machine.
- `heval` runs Harbor benchmark suites against those profiles and compares them. See [docs/heval.md](docs/heval.md).

The repo holds code, settings, and docs. Your data stays outside the repo: `huse` uses `~/.harness`, and `heval` uses `~/.heval`. See "Folders" below.

## Folders

### ~/.harness (huse data, never commit it)

`huse` makes these folders. To use another place, set `HARNESS_ROOT`.

```
~/.harness/
├── agents.system/                  your original ~/.agents (made by `huse setup`)
├── profiles/
│   ├── tuned/                      one folder for each profile (made by `huse new`)
│   │   ├── claude/                 used as CLAUDE_CONFIG_DIR
│   │   ├── codex/                  used as CODEX_HOME
│   │   ├── pi/                     used as PI_CODING_AGENT_DIR
│   │   └── agents/                 used as ~/.agents
│   └── lean/
│       └── ...
```

`tuned` and `lean` are example profile names. If your original `~/.agents` was a symlink (for example, into a dotfiles repo), `agents.system` is a symlink to the same folder.

`~/.agents` is a symlink that `huse` points at one of these folders:

```
~/.agents -> ~/.harness/agents.system          your normal setup
~/.agents -> ~/.harness/profiles/tuned/agents  while you use the profile "tuned"
```

### ~/.heval (heval data, never commit it)

`heval` keeps its logins and results in `~/.heval`. It only reads the profiles in `~/.harness`. See [docs/heval.md](docs/heval.md#files) for the layout.

### The repo (code and settings, commit it)

```
harness-tools/
├── bin/
│   ├── huse                        the profile tool
│   └── heval                       the eval tool
├── lib/                            Python files that heval uses with Harbor
├── tests/                          tests for both tools
├── docs/heval.md                   heval docs
├── .github/workflows/ci.yml        CI: lint and tests on Linux and macOS
├── eval.conf                       heval settings: suite, models, versions
├── eval.env.example                template for ~/.heval/eval.env
├── Makefile                        make check, make test, make lint
├── pyproject.toml                  version, dev tools, test settings
├── AGENTS.md                       instructions for coding agents
├── CHANGELOG.md
└── README.md
```

## Install

1. Clone or copy the repo, for example to `~/code/harness-tools`.
2. Add the repo's `bin/` folder to your `PATH` in `~/.zshrc` (use your repo path):

   ```sh
   export PATH="$HOME/code/harness-tools/bin:$PATH"
   ```

3. Open a new shell. Then `huse` and `heval` work from any folder.
4. Do the one-time setup of `~/.agents`. See "Set up ~/.agents (one time)" below.
5. Optional: to let `huse use` change the current shell, add this line after the `PATH` line. See "Two ways to use a profile" below.

   ```sh
   eval "$(huse init)"
   ```

Before you use `heval`, do its one-time setup in [docs/heval.md](docs/heval.md).

## Use huse

### Profiles

A profile is a named set of settings for Claude Code, Codex, and pi. You choose the name when you make the profile with `huse new`. In this README, `<profile>` means that name.

The examples use `tuned` and `lean` as profile names. Replace them with your own names. `huse ls` shows the names of your profiles.

`system` is a special name, not a profile. It means your normal setup: `~/.claude`, `~/.codex`, `~/.pi/agent`, and your original `~/.agents`.

`huse use <profile>` switches everything together:

- **Settings (this shell only):** `huse` sets `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `PI_CODING_AGENT_DIR` to the profile's folders.
- **`~/.agents` (all shells):** `huse` points the `~/.agents` symlink at the profile's `agents/` folder. Codex and pi read skills from `~/.agents/skills`, and this path has no environment variable. Thus, this change applies to all shells.

Only one profile can have `~/.agents` at a time. If you use two profiles in two shells at the same time, the last `huse use` gets `~/.agents`, and `huse` prints a note. `huse status` shows which profile has `~/.agents`.

`huse` does not change project files, for example `AGENTS.md`, `CLAUDE.md`, `.claude/`, or `.agents/` in a repo.

### Set up ~/.agents (one time)

`huse` must manage `~/.agents` before it can switch it. Do these steps one time:

1. Stop all running agents.
2. Make a backup: `cp -a ~/.agents ~/.agents.backup`
3. Run `huse setup`.

`huse` moves your `~/.agents` folder to `~/.harness/agents.system`. Then it replaces `~/.agents` with a symlink to that folder. The content does not change, so your agents work as before. If `~/.agents` is a git repo, the repo moves with it, and git still works there. This folder is what `system` means for `~/.agents`.

If `~/.agents` is already a symlink (for example, into a dotfiles repo), `huse` does not move anything. It saves a link to the real folder as `~/.harness/agents.system`. Your edits still go to your dotfiles.

If you do not have `~/.agents`, `huse` makes an empty `~/.harness/agents.system`.

`huse use` and `huse run` do not work until you run `huse setup`.

Run `huse status` to check the result. When you do not need the backup, delete `~/.agents.backup`.

### Create a profile

The command is `huse new <profile> [--from system|<other profile>]`. For example:

```sh
huse new tuned --from system    # makes "tuned", a copy of your normal setup
huse new lean                   # makes "lean", an empty profile
huse new tuned-v2 --from tuned  # makes "tuned-v2", a copy of the profile "tuned"
```

Each profile is a folder with one part for each harness:

```
~/.harness/profiles/<profile>/
  claude/   used as CLAUDE_CONFIG_DIR     settings.json, CLAUDE.md, skills/, agents/, commands/
  codex/    used as CODEX_HOME            config.toml, AGENTS.md
  pi/       used as PI_CODING_AGENT_DIR   settings.json, AGENTS.md, extensions/
  agents/   used as ~/.agents             skills/, AGENTS.md   (only the skills and files that this profile needs)
```

To change a profile, edit the files in its folder.

`--from` copies config files only. It does not copy logins, sessions, history, logs, or caches. Symlinks copy as symlinks. Thus, if a skill is a link into a repo, an edit in the profile changes the original.

Claude Code keeps user-scope MCP servers in `~/.claude.json`, outside `~/.claude`. `--from system` does not copy this file. Add the MCP servers again in the profile.

Claude Code reads skills from its own `skills/` folder, not from `~/.agents`. For Claude to use the same skills as Codex and pi, link its folder to `~/.agents/skills`. Set `p` to your profile name first:

```sh
p=tuned
rm -rf ~/.harness/profiles/$p/claude/skills   # only if it is a copy you do not need
ln -s ~/.agents/skills ~/.harness/profiles/$p/claude/skills
```

If `claude/skills` is already a link to `~/.agents/skills`, skip this step. After the link, Claude uses the same skills as Codex and pi when you use the profile.

### Log in to a profile

Logins do not copy. Log in one time in each profile, for each harness that you use. For the profile `tuned`:

```sh
huse run tuned claude        # then type /login
huse run tuned codex login
huse run tuned pi            # then type /login
```

### Two ways to use a profile

A program cannot change the environment of the shell that started it. Thus, `huse use <profile>` works in one of two ways:

- **Without shell integration (the default):** `huse use <profile>` switches `~/.agents` and opens a new shell with the profile's settings. Type `exit` to go back to your normal shell. Then `~/.agents` also goes back to what it was before, unless another shell changed it in the meantime. In a huse shell, `huse use` does not work again. Type `exit` first.
- **With shell integration:** add `eval "$(huse init)"` to `~/.zshrc` or `~/.bashrc`. Then `huse use <profile>` changes the current shell, and `huse off` changes it back. `~/.agents` stays on the profile until you run `huse off` or `huse use` again. The `eval` line only defines a small `huse` function that calls `bin/huse`.

`huse run <profile> <command>` works the same way in both modes. It switches the settings and `~/.agents` for one command. When the command ends, `~/.agents` goes back.

### Switch profiles

This example uses the profiles `tuned` and `lean`:

```sh
huse use tuned        # settings and ~/.agents switch to "tuned"
huse run lean codex   # one command with "lean"; after it, ~/.agents goes back to "tuned"
exit                  # without integration: leave the "tuned" shell; ~/.agents goes back
huse off              # with integration: settings and ~/.agents go back to your normal setup
```

### Command list

| Command | Effect |
| --- | --- |
| `huse setup` | One time: let `huse` manage `~/.agents`. |
| `huse new <profile> [--from system\|<other profile>]` | Make a profile, empty or copied. |
| `huse use <profile>` | Use a profile: its settings and its `~/.agents`. Without integration, this opens a new shell. |
| `huse off` | With integration, go back to your normal setup. In a huse shell without integration, type `exit`. |
| `huse run <profile> <command> [args...]` | Run one command with a profile. `~/.agents` goes back after it. |
| `huse ls` | List your profiles. `*` marks the profile of this shell. `(~/.agents)` marks the profile that has `~/.agents`. |
| `huse status` | Show the profile of this shell and the profile that has `~/.agents`. |
| `huse init` | Print the shell integration. Use it as `eval "$(huse init)"`. |

To show the active profile in your zsh prompt:

```sh
setopt PROMPT_SUBST
RPROMPT='${HARNESS_PROFILE:+[$HARNESS_PROFILE]}'
```

## Development

```sh
pip install --group dev    # pip 25.1 or later. Or: uv sync --group dev
make check                 # shellcheck, ruff, and all tests
```

- The tests run in a temporary home folder. They do not change your `~/.agents`, `~/.harness`, or `~/.heval`.
- The Harbor tests need Harbor: `pip install --group harbor`, then `make test-harbor`. Without Harbor, they skip.
- On macOS, `make test-bash32` runs the tests with `/bin/bash` (Bash 3.2).
- `AGENTS.md` lists the rules that each change must keep.

## Environment variables

| Variable | Default | Use |
| --- | --- | --- |
| `HARNESS_ROOT` | `~/.harness` | Where profiles and data are kept. |
| `HARNESS_PROFILE` | (set by `huse use`) | The profile name of this shell. Read it, do not set it. |
