# heval

`heval` runs Harbor benchmark suites against your harness profiles and compares the results. It uses your CLI logins, not API keys.

You make the profiles with `huse`. See the [main README](../README.md#use-huse).

## Commands

| Command | Effect |
| --- | --- |
| `heval check` | Run the reference solutions. Every task must pass on your machine. |
| `heval run <claude\|codex\|pi> <profile> [harbor args]` | Run the suite with one harness and one profile. Add `--dry-run` to check first. |
| `heval compare <claude\|codex\|pi> <base profile> <new profile>` | Compare two profiles, paired per task. |
| `heval resume <job>` | Run again the trials that stopped on a usage limit or an error. |
| `heval jobs` | List jobs. |
| `heval view` | Open the Harbor results viewer. |

## Files

| File | Purpose |
| --- | --- |
| `eval.conf` (repo) | Suite, number of tasks, attempts, models, and versions. Commit it. |
| `eval.env.example` (repo) | Template for your logins. |
| `~/.harness/eval.env` | Your logins. Never commit it. |
| `~/.harness/eval-codex/`, `~/.harness/eval-pi/` | Separate Codex and pi logins for evals. |
| `~/.harness/jobs/` | Harbor results. |

## One-time setup

1. Install Docker and start it. Install Harbor: `uv tool install harbor`.
2. Edit `eval.conf` in the repo. Set `DATASET` with a pinned version (see `harbor datasets list`). Set one model for each harness, and pin the harness versions. Commit the file.
3. Make the eval logins:

   ```sh
   claude setup-token                                   # copy the token

   mkdir -p ~/.harness/eval-codex
   echo 'cli_auth_credentials_store = "file"' > ~/.harness/eval-codex/config.toml
   CODEX_HOME=~/.harness/eval-codex codex login

   PI_CODING_AGENT_DIR=~/.harness/eval-pi pi           # type /login, select ChatGPT Plus/Pro (Codex)
   ```

4. Copy `eval.env.example` from the repo to `~/.harness/eval.env`. Paste the Claude token. Run `chmod 600 ~/.harness/eval.env`.
5. Make a frozen baseline: `huse new base --from system` (see [Create a profile](../README.md#create-a-profile)). Your daily setup changes over time, so do not use `system` as the baseline.
6. Run `heval check`. The oracle agent must pass every task. Add the names of tasks that fail to `EXCLUDE_TASKS` in `eval.conf`.

## Each experiment

`base` and `skills-v2` are example profile names. Replace them with your own names.

```sh
huse new skills-v2 --from base          # then change ONE thing in ~/.harness/profiles/skills-v2
heval run claude skills-v2 --dry-run    # shows what heval sends
heval run claude base                   # the baseline: run it one time only
heval run claude skills-v2
heval compare claude base skills-v2
heval resume <job>                      # after a usage limit resets (names: heval jobs)
heval view                              # read the trajectories
```

Do not edit a profile after you run it. `heval compare` uses all jobs with the same profile name. Make a new profile for each change.

## What heval takes from a profile

- Skills: `agents/skills`, and also `claude/skills` for Claude if it is a different folder.
- Global instructions: `claude/CLAUDE.md`, `codex/AGENTS.md`, or `pi/AGENTS.md`. If there is no such file, `heval` uses `agents/AGENTS.md`. `@` imports do not work in the container, so put the full text in the file.
- Native config (optional): `claude/eval-settings.json` or `codex/eval-config.toml`. Use a separate file with only the settings that you want to test. Your daily settings can point to hooks and scripts that are not in the container.
- Not included: hooks, plugins, MCP servers, and pi settings and extensions.

## Rules for a fair result

- Do not change `eval.conf` between the runs that you compare.
- If the model or harness version changes, run the baseline again. `heval compare` warns when versions differ.
- Trials that stop on a usage limit or an API error do not count. Run them again with `heval resume`.
- "No clear change" is a valid result. A small change usually needs more tasks to show.

## Environment variables

| Variable | Default |
| --- | --- |
| `HARNESS_ROOT` | `~/.harness` |
| `HEVAL_CONF` | `<repo>/eval.conf` |
| `HEVAL_ENV` | `$HARNESS_ROOT/eval.env` |
| `JOBS_DIR` | `$HARNESS_ROOT/jobs` |
