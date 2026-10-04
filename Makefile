# =============================================================================
# WBMS-Lite task runner
#
# Works on macOS, Linux, WSL and Git Bash. List every command with:  make help
# Native Windows (PowerShell, no make installed): use  .\tasks.ps1 <task>
# The task names are identical in both files.
#
# Override the interpreter if needed:   make venv PYTHON=python3
# =============================================================================

VENV      := .venv
FLASK_APP ?= wbms:create_app

ifeq ($(OS),Windows_NT)
    PYTHON ?= python
    PY     := $(VENV)/Scripts/python.exe
else
    PYTHON ?= python3.12
    PY     := $(VENV)/bin/python
endif

# Lets "import wbms" work without installing the package (src layout).
export PYTHONPATH := src

.DEFAULT_GOAL := help
.PHONY: help venv install run test cov lint format initdb clean

help: ## Show this list of commands
	@echo "WBMS-Lite tasks (usage: make <target>)"
	@echo
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-8s %s\n", $$1, $$2}'

# File target: only runs when .venv/bin/python is missing, so it is safe to repeat.
# The leading "-" lets the pip upgrade fail (offline) without losing the new venv.
$(PY):
	$(PYTHON) -m venv $(VENV)
	-$(PY) -m pip install --upgrade pip

venv: $(PY) ## Create the .venv virtual environment (once)
	@echo "Virtual environment ready in $(VENV)"

install: $(PY) ## Install runtime and dev dependencies into .venv
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt

run: $(PY) ## Start the Flask dev server in debug mode
	$(PY) -m flask --app $(FLASK_APP) run --debug

test: $(PY) ## Run the test suite with pytest
	$(PY) -m pytest -v

cov: $(PY) ## Run tests with a coverage report; fails below 80 percent
	$(PY) -m pytest --cov=wbms --cov-report=term-missing --cov-report=html --cov-fail-under=80

lint: $(PY) ## Check the code with ruff
	$(PY) -m ruff check .

format: $(PY) ## Auto-format the code with ruff
	$(PY) -m ruff format .

initdb: $(PY) ## Create the SQLite database from schema.sql
	$(PY) scripts/init_db.py

clean: ## Remove caches and coverage output (keeps .venv)
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name htmlcov \) -not -path "./$(VENV)/*" -prune -exec rm -rf {} +
	rm -f .coverage
