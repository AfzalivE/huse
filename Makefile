# Development tasks. Install the tools first:  pip install --group dev   (or: uv sync --group dev)
PYTHON ?= python3
SCRIPTS := bin/huse bin/heval
PYFILES := lib tests
BASH32  ?= /bin/bash

.PHONY: check lint format test test-harbor test-agents test-bash32

check: lint test          ## lint and test (run this before each commit)

lint:                     ## shellcheck and ruff
	shellcheck -x $(SCRIPTS)
	$(PYTHON) -m ruff check $(PYFILES)
	$(PYTHON) -m ruff format --check $(PYFILES)

format:                   ## fix what ruff can fix
	$(PYTHON) -m ruff check --fix $(PYFILES)
	$(PYTHON) -m ruff format $(PYFILES)

test:                     ## all tests (Harbor tests skip if harbor is not installed)
	$(PYTHON) -m pytest

test-harbor:              ## only the tests that need harbor (pip install --group harbor)
	$(PYTHON) -m pytest -m harbor

test-agents:              ## only the tests with the real codex and pi (npm install -g @openai/codex @earendil-works/pi-coding-agent)
	$(PYTHON) -m pytest -m agents

test-bash32:              ## all tests with Bash 3.2, the macOS /bin/bash (set BASH32 elsewhere)
	@d=$$(mktemp -d) && ln -s "$(BASH32)" "$$d/bash" && \
	  PATH="$$d:$$PATH" TEST_BASH="$(BASH32)" $(PYTHON) -m pytest -m "not harbor"; \
	  rc=$$?; rm -rf "$$d"; exit $$rc
