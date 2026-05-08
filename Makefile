SHELL := /bin/bash

.DEFAULT_GOAL := help

PYTHON ?= python3
VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(PY) -m pip
LBD := $(VENV)/bin/lbd

.PHONY: help install-dev lint test compile docs docs-check build smoke ci lbd clean

# Allow passing CLI args as extra "targets":
#   make lbd -- --help
#   make lbd -- --json q "Heat"
#   make lbd -- q "Heat" --format json
ifneq ($(filter lbd,$(MAKECMDGOALS)),)
RUN_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
$(eval $(RUN_ARGS):;@:)
endif

help:
	@printf '%s\n' \
		'Targets:' \
		'  make install-dev  Create .venv and install editable dev dependencies' \
		'  make lint         Run Ruff' \
		'  make test         Run pytest' \
		'  make compile      Compile Python sources' \
		'  make docs         Regenerate docs/COMMANDS.md' \
		'  make docs-check   Regenerate command docs and require no diff' \
		'  make build        Build sdist and wheel into dist/' \
		'  make smoke        Install built wheel in a fresh temp venv and run lbd --help' \
		'  make ci           Full local gate: lint, test, compile, docs-check, build, smoke' \
		'  make lbd -- ...   Run the local editable lbd command'

$(PY):
	$(PYTHON) -m venv $(VENV)

install-dev: $(PY)
	$(PIP) install --upgrade pip
	$(PIP) install -e '.[dev]'

lint: install-dev
	$(VENV)/bin/ruff check .

test: install-dev
	$(PY) -m pytest -q

compile: install-dev
	$(PY) -m compileall -q letterboxd_cli tests

docs: install-dev
	$(PY) scripts/gen-command-docs.py docs/COMMANDS.md

docs-check: docs
	git diff --exit-code -- docs/COMMANDS.md

build: install-dev
	$(PIP) install build
	rm -rf build dist *.egg-info
	$(PY) -m build

smoke: build
	rm -rf /tmp/letterboxd-cli-smoke
	rm -rf /tmp/letterboxd-cli-smoke-data
	$(PYTHON) -m venv /tmp/letterboxd-cli-smoke
	/tmp/letterboxd-cli-smoke/bin/python -m pip install dist/*.whl
	/tmp/letterboxd-cli-smoke/bin/lbd --help >/dev/null
	/tmp/letterboxd-cli-smoke/bin/lbd version --format json >/dev/null
	mkdir -p /tmp/letterboxd-cli-smoke-data/export
	printf 'Date,Name,Year,Letterboxd URI\n2026-04-21,Heat,1995,https://boxd.it/def\n' > /tmp/letterboxd-cli-smoke-data/export/watchlist.csv
	/tmp/letterboxd-cli-smoke/bin/lbd --db /tmp/letterboxd-cli-smoke-data/lbd.sqlite3 load /tmp/letterboxd-cli-smoke-data/export >/dev/null
	/tmp/letterboxd-cli-smoke/bin/lbd --db /tmp/letterboxd-cli-smoke-data/lbd.sqlite3 --json watchlist | grep -q '"Heat"'
	/tmp/letterboxd-cli-smoke/bin/lbd --db /tmp/letterboxd-cli-smoke-data/lbd.sqlite3 sql 'SELECT 1 AS one' --format json | grep -q '"one": 1'

ci: lint test compile docs-check build smoke

lbd: install-dev
	@if [ -n "$(RUN_ARGS)" ]; then \
		$(LBD) $(RUN_ARGS); \
	elif [ -n "$(ARGS)" ]; then \
		$(LBD) $(ARGS); \
	else \
		$(LBD) --help; \
	fi

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
	find letterboxd_cli tests -type d -name __pycache__ -prune -exec rm -rf {} +
