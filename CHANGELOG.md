# Changelog

## 0.1.0

First release.

- `huse`: make harness profiles (`new`), switch the settings and `~/.agents` together (`use`, `off`, `run`), and take over `~/.agents` one time (`setup`). Works without shell integration (a new shell) or with `eval "$(huse init)"`.
- `heval`: run Harbor benchmark suites against profiles with your CLI logins (`check`, `run`), run limit-stopped trials again (`resume`), and compare two profiles paired per task (`compare`). Keeps its logins and results in `~/.heval`, apart from the huse profiles.
- Tests for both tools, including Bash 3.2 and zsh, and CI on Linux and macOS.
