"""Harbor agents that load parts of a harness profile that Harbor has no field for.

Each class is Harbor's built-in agent plus one setup step:
  - HARNESS_INSTRUCTIONS=<file>  copy this file to the agent's native global
                                 instruction file (CLAUDE.md or AGENTS.md).
  - PI_AUTH_JSON_PATH=<file>     (pi only) copy a pi subscription login.

The `heval` command sets these variables for you. To use by hand:
  PYTHONPATH=<repo>/lib harbor run ... -a harbor_profile_agents:ClaudeCodeProfile
"""

import shlex
from pathlib import Path

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.installed.codex import Codex
from harbor.agents.installed.pi import Pi
from harbor.environments.base import BaseEnvironment


async def _put_file(agent, environment: BaseEnvironment, src: Path, remote_dir: str, name: str) -> None:
    """Upload src to "<remote_dir>/<name>" as the agent user. remote_dir may contain $HOME."""
    tmp = f"/tmp/harbor-profile-{name}"
    await environment.upload_file(src, tmp)
    if environment.default_user is not None:
        user = shlex.quote(str(environment.default_user))
        await agent.exec_as_root(environment, command=f"chown {user} {tmp}")
    await agent.exec_as_agent(
        environment,
        command=(f'mkdir -p "{remote_dir}" && mv {tmp} "{remote_dir}/{name}" && chmod 600 "{remote_dir}/{name}"'),
    )


def _file_from_env(agent, var: str) -> Path | None:
    value = agent._get_env(var)
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_file():
        raise RuntimeError(f"{var} points to a missing file: {path}")
    # Upload the real file. Harbor uploads with `docker cp`, which copies a symlink as a
    # symlink, and its target does not exist in the container.
    return path.resolve()


class ClaudeCodeProfile(ClaudeCode):
    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        if src := _file_from_env(self, "HARNESS_INSTRUCTIONS"):
            # Harbor runs Claude Code with CLAUDE_CONFIG_DIR=<agent logs>/sessions.
            config_dir = (self.environment_logs_dir / "sessions").as_posix()
            await _put_file(self, environment, src, config_dir, "CLAUDE.md")


class CodexProfile(Codex):
    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        if src := _file_from_env(self, "HARNESS_INSTRUCTIONS"):
            await _put_file(self, environment, src, self._REMOTE_CODEX_HOME.as_posix(), "AGENTS.md")


class PiProfile(Pi):
    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        if src := _file_from_env(self, "PI_AUTH_JSON_PATH"):
            await _put_file(self, environment, src, "$HOME/.pi/agent", "auth.json")
        elif (self.model_name or "").startswith("openai-codex/"):
            # Fail the setup: then the trial is an error, not a graded failure.
            raise RuntimeError("pi needs a subscription login for openai-codex: set PI_AUTH_JSON_PATH")
        if src := _file_from_env(self, "HARNESS_INSTRUCTIONS"):
            await _put_file(self, environment, src, "$HOME/.pi/agent", "AGENTS.md")
