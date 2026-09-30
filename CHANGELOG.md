# Changelog

## 0.1.0

First release.

- `huse`: make harness profiles (`new`) and use them one shell at a time (`use`, `off`, `run`). A profile sets `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `PI_CODING_AGENT_DIR`. Skills are kept one time in a store (`~/.harness/skills`), and each profile links the skills that it uses (`huse skill`). `huse setup` moves the skills in `~/.agents/skills` to the store, because Codex and pi read that folder in every profile. `huse status` warns when it has skills again. Works without shell integration (a new shell) or with `eval "$(huse init)"`.
- `heval`: run Harbor benchmark suites against profiles with your CLI logins (`check`, `run`), run limit-stopped and login-stopped trials again (`resume`), and compare two profiles paired per task (`compare`). Keeps its logins and results in `~/.heval`, apart from the huse profiles.
- `heval check` prints the tasks that failed the oracle run, ready to paste into `EXCLUDE_TASKS`.
- Tests for both tools, including Bash 3.2, zsh, and the real Codex and pi, and CI on Linux and macOS.
