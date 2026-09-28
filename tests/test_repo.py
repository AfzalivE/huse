"""Checks that keep the code, the help texts, and the docs in sync."""

import re
import tomllib

from conftest import REPO, heval, huse

VERSION = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"]


def test_versions_match_pyproject(env):
    assert huse("--version", env=env).stdout.strip() == f"huse {VERSION}"
    assert heval("--version", env=env).stdout.strip() == f"heval {VERSION}"


def test_changelog_has_current_version():
    assert f"## {VERSION}" in (REPO / "CHANGELOG.md").read_text()


def doc_commands(path, tool):
    """Commands in the command table of a doc: rows that start with | `tool <cmd>."""
    return set(re.findall(rf"^\| `{tool} ([a-z-]+)", path.read_text(), flags=re.M))


def test_huse_help_and_readme_list_the_same_commands(env):
    in_help = set(re.findall(r"^  huse ([a-z-]+)", huse("help", env=env).stderr, flags=re.M))
    assert doc_commands(REPO / "README.md", "huse") == in_help - {"--version"}


def test_heval_usage_and_doc_list_the_same_commands(env):
    in_usage = set(re.findall(r"^  heval ([a-z-]+)", heval("help", env=env).stdout, flags=re.M))
    assert doc_commands(REPO / "docs/heval.md", "heval") == in_usage - {"--version"}


def test_login_files_are_ignored_by_git():
    ignored = (REPO / ".gitignore").read_text().split()
    assert "eval.env" in ignored and "jobs/" in ignored


def test_eval_conf_is_pinned():
    conf = (REPO / "eval.conf").read_text()
    dataset = re.search(r'^DATASET="([^"]+)"', conf, flags=re.M).group(1)
    assert re.fullmatch(r"[\w.-]+/[\w.-]+@\d+(\.\d+)*", dataset), "DATASET must pin a version"
