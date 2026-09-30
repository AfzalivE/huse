# harness-tools

Two tools for agent harness profiles (Claude Code, Codex, pi):

- `huse` lets you build a new harness setup in one shell, while your main setup stays in all other shells.
- `heval` runs Harbor benchmark suites against those profiles and compares them. See [docs/heval.md](docs/heval.md).

## What huse is for

Use `huse` to try a new harness setup without risk to your main setup:

1. Make a profile from scratch: `huse new <profile>`.
2. Use it in one shell: `huse use <profile>`. All other shells, and your desktop apps, keep your main setup.
3. Log in, add skills and instructions, and work with it.
4. When it is ready, make it your main setup: `huse promote <profile>`. If you do not want it, delete its folder, `~/.harness/profiles/<profile>`.

`huse` is not a tool to switch between many profiles every day. Each profile has its own logins, sessions, and history. A session that you start in a profile resumes only in that profile. Keep a profile only while you try it. Then promote it or delete it.

The repo holds code, settings, and docs. Your data stays outside the repo: `huse` uses `~/.harness`, and `heval` uses `~/.heval`. See "Folders" below.

## Folders

### ~/.harness (huse data, never commit it)

`huse` makes these folders. To use another place, set `HARNESS_ROOT`.

```
~/.harness/
├── skills/                         the skill store: one folder for each skill
│   └── <skill>/
└── profiles/
    ├── tuned/                      one folder for each profile (made by `huse new`)
    │   ├── claude/                 used as CLAUDE_CONFIG_DIR
    │   │   └── skills/<skill> -> ~/.harness/skills/<skill>
    │   ├── codex/                  used as CODEX_HOME
    │   │   └── skills/<skill> -> ~/.harness/skills/<skill>
    │   └── pi/                     used as PI_CODING_AGENT_DIR
    │       └── skills/<skill> -> ~/.harness/skills/<skill>
    └── lean/
        └── ...
```

`tuned` and `lean` are example profile names. See "How it works" below.

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
├── CLAUDE.md                       loads AGENTS.md in Claude Code
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
4. Optional: to let `huse use` change the current shell, add this line after the `PATH` line. See "Two ways to use a profile" below.

   ```sh
   eval "$(huse init)"
   ```

Before you use `heval`, do its one-time setup in [docs/heval.md](docs/heval.md).

## Use huse

### Profiles

A profile is a named set of settings for Claude Code, Codex, and pi. You choose the name when you make the profile with `huse new`. In this README, `<profile>` means that name.

The examples use `tuned` and `lean` as profile names. Replace them with your own names. `huse ls` shows the names of your profiles.

`system` is a special name, not a profile. It means your normal setup: `~/.claude`, `~/.codex`, and `~/.pi/agent`.

`huse use <profile>` changes only the current shell. Other shells, and apps that do not start from a shell, keep your normal setup. `huse` does not change project files, for example `AGENTS.md`, `CLAUDE.md`, `.claude/`, or `.agents/` in a repo.

### How it works

- **Settings:** `huse` sets `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `PI_CODING_AGENT_DIR` to the profile's folders. It does not change `HOME` or `PATH`.
- **Skills:** each harness reads skills from the `skills/` folder in its config folder. `huse` keeps each skill one time, in the store `~/.harness/skills`. A profile uses a skill through a link in its harness folders. `huse skill add` makes the links. See "Skills" below.
- **`~/.agents/skills`:** Codex and pi also read this folder, in every profile. Thus, `huse setup` moves its skills to the store one time. After that, each profile chooses its own skills.

Limits:

- **Codex marks `$CODEX_HOME/skills` as deprecated.** It still works (tested with Codex 0.159.0). If Codex removes it, profiles lose their skills in Codex. The CI job `agents` tests the newest Codex, so this shows up there.
- **Tools that install into `~/.agents/skills`,** for example `npx skills add -g`, put skills where every profile sees them. `huse status` warns about this. Run `huse setup` again to move them to the store.
- **Other programs that read `~/.agents/skills`** do not see the skills after `huse setup`. Link a skill back if a program needs it.

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
  codex/    used as CODEX_HOME            config.toml, AGENTS.md, skills/
  pi/       used as PI_CODING_AGENT_DIR   settings.json, AGENTS.md, skills/, extensions/
```

To change a profile, edit the files in its folder.

`--from` copies config files only. It does not copy logins, sessions, history, logs, or caches. Symlinks copy as symlinks. Thus, the copy uses the same skills of the store, and if a skill is a link into a repo, an edit in the profile changes the original.

Claude Code keeps user-scope MCP servers in `~/.claude.json`, outside `~/.claude`. `--from system` does not copy this file. Add the MCP servers again in the profile.

### Skills

Do this one time. It moves the skills in `~/.agents/skills` to the store `~/.harness/skills`, and links them into `~/.codex/skills` and `~/.pi/agent/skills`. Your normal setup keeps the same skills:

```sh
huse setup
```

To add a new skill, put its folder in `~/.harness/skills`. Then choose the profiles that use it. In these examples, `web-design` is an example skill name:

```sh
huse skill ls tuned                      # the skills in the store, and which harnesses of "tuned" use them
huse skill add tuned web-design          # Claude Code, Codex, and pi of "tuned" use the skill
huse skill add lean web-design codex     # only Codex of "lean" uses the skill
huse skill rm tuned web-design pi        # pi of "tuned" stops using the skill
huse skill add system web-design claude  # your normal setup of Claude Code uses the skill
```

`huse skill rm` removes only links to the store. It never deletes a skill. A real skill folder in a harness folder also works, but only that profile has it.

### Make a profile your main setup

Try a new setup in one shell. When it is ready, make it your main setup. In this example, `tuned` is an example profile name:

```sh
huse new tuned            # an empty profile, from scratch
huse use tuned            # only this shell uses it: log in, add skills, try it
huse promote tuned        # "tuned" becomes your main setup
huse promote before-tuned # go back to the old main setup
```

`huse promote <profile>` does these steps:

1. It moves the config of your main setup into a new profile, `before-<profile>`. If that name exists, it adds a number. To choose the name, add `--save-as <name>`.
2. It copies the config of the profile into `~/.claude`, `~/.codex`, and `~/.pi/agent`.

Only these config entries move. Logins, sessions, history, and caches stay in your main folders, so you can still resume your sessions:

| Harness | Config entries |
| --- | --- |
| Claude Code | `settings.json`, `CLAUDE.md`, `skills/`, `agents/`, `commands/`, `hooks/`, `output-styles/`, `plugins/`, `keybindings.json` |
| Codex | `config.toml`, `AGENTS.md`, `skills/`, `rules/`, `prompts/`, `hooks.json`, `plugins/` |
| pi | `settings.json`, `AGENTS.md`, `SYSTEM.md`, `APPEND_SYSTEM.md`, `skills/`, `extensions/`, `prompts/`, `themes/`, `models.json`, `keybindings.json` |

Sessions that you made in the profile stay in the profile. Links copy as links. If a main config file is a link into your dotfiles, the saved profile keeps the link, and the promoted file replaces it.

### Log in to a profile

Logins do not copy. Log in one time in each profile, for each harness that you use. For the profile `tuned`:

```sh
huse run tuned claude        # then type /login
huse run tuned codex login
huse run tuned pi            # then type /login
```

### Two ways to use a profile

A program cannot change the environment of the shell that started it. Thus, `huse use <profile>` works in one of two ways:

- **Without shell integration (the default):** `huse use <profile>` opens a new shell with the profile. Type `exit` to go back to your normal shell. In a huse shell, `huse use` does not work again. Type `exit` first.
- **With shell integration:** add `eval "$(huse init)"` to `~/.zshrc` or `~/.bashrc`. Then `huse use <profile>` changes the current shell, and `huse off` changes it back. The `eval` line only defines a small `huse` function that calls `bin/huse`.

`huse run <profile> <command>` works the same way in both modes. It uses the profile for one command.

### Switch profiles

This example uses the profiles `tuned` and `lean`:

```sh
huse use tuned        # this shell uses "tuned"; other shells do not change
codex                 # Codex with the settings and skills of "tuned"
huse run lean pi      # one command with "lean"
exit                  # without integration: leave the "tuned" shell
huse off              # with integration: this shell goes back to your normal setup
```

You can use different profiles in different shells at the same time.

### Command list

| Command | Effect |
| --- | --- |
| `huse new <profile> [--from system\|<other profile>]` | Make a profile, empty or copied. |
| `huse use <profile>` | Use a profile in this shell. Without integration, this opens a new shell. |
| `huse off` | With integration, go back to your normal setup. In a huse shell without integration, type `exit`. |
| `huse run <profile> <command> [args...]` | Run one command with a profile. |
| `huse ls` | List your profiles. `*` marks the profile of this shell. |
| `huse promote <profile> [--save-as <profile>]` | Make a profile your main setup. Save the old main config as a profile. See "Make a profile your main setup". |
| `huse status` | Show the profile of this shell and its folders. Warn if `~/.agents/skills` has skills. |
| `huse setup` | Move the skills in `~/.agents/skills` to the store. Your normal setup of Codex and pi keeps them. |
| `huse skill ls\|add\|rm ...` | List the skills in the store. Add or remove a skill in a profile. See "Skills". |
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
- The tests in `tests/test_agents_real.py` use the real `codex` and `pi`, without a model or a login. They check that both read the profile's skills through `CODEX_HOME` and `PI_CODING_AGENT_DIR`. Without them, these tests skip. Install them with `npm install -g @openai/codex @earendil-works/pi-coding-agent`, then run `make test-agents`.
- `AGENTS.md` lists the rules that each change must keep.

## Environment variables

| Variable | Default | Use |
| --- | --- | --- |
| `HARNESS_ROOT` | `~/.harness` | Where profiles and data are kept. |
| `HARNESS_PROFILE` | (set by `huse use`) | The profile name of this shell. Read it, do not set it. |
