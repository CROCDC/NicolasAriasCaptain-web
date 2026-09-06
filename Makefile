# =============================================================================
# Capitán Nicolás Arias — Developer Makefile
# Usage: make <target>
# =============================================================================

PYTHON := python3.12
VENV   := venv
PIP    := $(VENV)/bin/pip
PY     := $(VENV)/bin/python
PORT   := $(shell awk 'BEGIN{srand(); print int(rand()*4000+5000)}')

.DEFAULT_GOAL := help

# -----------------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------------
.PHONY: help
help:
	@echo ""
	@echo "  Capitán Nicolás Arias — available targets"
	@echo ""
	@echo "  make install    Create virtualenv and install dependencies"
	@echo "  make dev        Start local dev server (random port 5000-9000)"
	@echo "  make test       Run the whole test suite"
	@echo "  make test-fast  Everything except the browser tests"
	@echo "  make browser    Install the Playwright browser the suite drives"
	@echo "  make screenshots Rewrite the visual baseline for this renderer"
	@echo "  make photos     List the photographs the site is still waiting for"
	@echo "  make lint       Check code style (pycodestyle, 100 cols)"
	@echo "  make coverage   Run the fast suite and report coverage"
	@echo "  make clean      Remove venv and compiled files"
	@echo ""

# -----------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------
.PHONY: install
install: $(VENV)/bin/activate

$(VENV)/bin/activate: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip -q
	$(PIP) install -r requirements.txt -q
	@echo ""
	@echo "  Virtualenv ready. Run: make dev"
	@echo ""

# Playwright's browser is a separate download from the Python package, and the
# browser tests skip themselves without it — which is a green suite that checked
# nothing. Kept as its own target so `make install` stays quick.
.PHONY: browser
browser: $(VENV)/bin/activate
	$(PY) -m playwright install firefox

# -----------------------------------------------------------------------------
# Development server
# -----------------------------------------------------------------------------
.PHONY: dev
dev: $(VENV)/bin/activate
	$(PY) -c "from app import app; app.run(debug=True, host='0.0.0.0', port=$(PORT))"

# -----------------------------------------------------------------------------
# Testing
# -----------------------------------------------------------------------------
.PHONY: test
test: $(VENV)/bin/activate
	$(VENV)/bin/pytest tests/ -v

.PHONY: test-fast
test-fast: $(VENV)/bin/activate
	$(VENV)/bin/pytest tests/ -q -m "not slow"

.PHONY: coverage
coverage: $(VENV)/bin/activate
	$(PY) -m coverage run --source=app -m pytest tests/ -q -m "not slow"
	$(PY) -m coverage report --sort=miss

# -----------------------------------------------------------------------------
# Visual baseline
# -----------------------------------------------------------------------------
# Rewrites tests/screenshots/<platform>-<browser>/ after an intended visual
# change. Look at the diff before committing it: that is the whole point of the
# baseline. A renderer with no committed set writes one on the first run and
# says so — the pictures are per browser and per operating system, because the
# same page is not the same pixels in two of them.
.PHONY: screenshots
screenshots: $(VENV)/bin/activate
	UPDATE_SCREENSHOTS=1 $(VENV)/bin/pytest -q tests/test_visual.py

# -----------------------------------------------------------------------------
# Photographs
# -----------------------------------------------------------------------------
# What the site declares in app/static/data/gallery.json and does not yet have
# a file for. Every name printed here is currently showing as a placeholder.
.PHONY: photos
photos: $(VENV)/bin/activate
	$(PY) scripts/check_photos.py

# -----------------------------------------------------------------------------
# Linting
# -----------------------------------------------------------------------------
.PHONY: lint
lint: $(VENV)/bin/activate
	$(VENV)/bin/pycodestyle app/ tests/ scripts/ run.py --max-line-length=100

# -----------------------------------------------------------------------------
# Clean
# -----------------------------------------------------------------------------
.PHONY: clean
clean:
	rm -rf $(VENV)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Cleaned."
