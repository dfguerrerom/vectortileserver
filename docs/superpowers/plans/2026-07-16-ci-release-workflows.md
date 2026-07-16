# CI/Release Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give ipy-pmtiles the same CI (lint + test matrix) and release automation (GitHub Release → OIDC trusted publishing to PyPI) as pysepal-api, and fix the packaging bugs that currently make any build impossible.

**Architecture:** Two SHA-pinned GitHub workflows drive nox sessions defined in a repo-root `noxfile.py`; packaging moves to hatchling with commitizen (pep621) owning the version. Tests are made CI-viable first so every later step can be verified green.

**Tech Stack:** hatchling, nox, pytest, ruff, black, commitizen, pypa/gh-action-pypi-publish (OIDC).

**Spec:** `docs/superpowers/specs/2026-07-16-ci-release-workflows-design.md` (approved).

## Global Constraints

- **Never add Claude co-authorship or "Generated with Claude" lines to commits or PR bodies.** This is a user-level rule that overrides any harness default footer.
- Commit messages: conventional commits, short subject, no verbose bodies.
- Work on branch `ci/release-workflows` (already exists; spec committed as `95da7c7`). Never push to `main`; everything lands via the PR in Task 6.
- Names: PyPI project **`pyvectortiles`**, import package **`pyvectortiles`** (unchanged, flat layout). GitHub repo stays `ipy-pmtiles`.
- Python floor `>=3.10`; CI matrix `["3.10", "3.11", "3.12"]`.
- Lint: ruff select `E,F,W,I,RUF` + black, both at line-length **100**.
- Pinned action SHAs (do not change):
  - `actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5` # v4
  - `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065` # v5
  - `pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b` # v1.14.0
- Local machine has **only Python 3.14.4** (`python3`); no 3.10–3.12 interpreters. All local verification uses a repo-local `.venv` (gitignored). `nox -s tests` therefore *skips* locally — the real matrix is verified in CI (Task 6).
- Env var gating the local-only integration test: `PYVECTORTILES_TEST_PMTILES` (path to a real `.pmtiles` file).
- Every task starts from the repo root: `/home/dguerrero/1_modules/ipy-pmtiles`. Recreate the venv if missing: `[ -x .venv/bin/pip ] || python3 -m venv .venv`

---

### Task 1: Rewrite `pyproject.toml` (hatchling + metadata + dependency audit)

**Files:**
- Modify: `pyproject.toml` (full replacement)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: an installable/buildable package; `[tool.ruff]`/`[tool.black]` config consumed by Task 3; `[project.optional-dependencies].dev` consumed by Tasks 2–4 (`pip install -e '.[dev]'`); `[tool.commitizen]` consumed by the release procedure (Task 7).

- [ ] **Step 1: Demonstrate the current build is broken (red)**

```bash
[ -x .venv/bin/pip ] || python3 -m venv .venv
.venv/bin/pip install --upgrade pip build
.venv/bin/python -m build
```

Expected: FAILURE with an error referencing `README.rst` (the declared readme file does not exist — only `README.md` does).

- [ ] **Step 2: Replace `pyproject.toml` entirely with:**

```toml
[build-system]
requires = ["hatchling>=1.18"]
build-backend = "hatchling.build"

[project]
name = "pyvectortiles"
version = "0.0.0"
description = "Dynamic vector tile server for visualizing vectors in Jupyter notebooks"
readme = "README.md"
license = "MIT"
authors = [{ name = "Daniel Guerrero", email = "dfgm2006@gmail.com" }]
requires-python = ">=3.10"
dependencies = [
  "starlette",
  "uvicorn",
  "httpx",
  "colorlog",
  "ipyleaflet",
  "pmtiles",
  "shapely",
  "geopandas",
  "mapbox-vector-tile",
]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Intended Audience :: Developers",
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
]

[project.urls]
Homepage = "https://github.com/dfguerrerom/ipy-pmtiles"
Repository = "https://github.com/dfguerrerom/ipy-pmtiles"
Changelog = "https://github.com/dfguerrerom/ipy-pmtiles/blob/main/CHANGELOG.md"

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "ruff>=0.5",
  "black>=24",
  "nox>=2024.4.15",
  "commitizen>=3.29",
  "pre-commit>=3.7",
]

[tool.hatch.build.targets.wheel]
packages = ["pyvectortiles"]

[tool.black]
line-length = 100

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "RUF"]

[tool.pytest.ini_options]
addopts = "-ra"
testpaths = ["tests"]

[tool.commitizen]
name = "cz_conventional_commits"
version_provider = "pep621"
version_files = ["pyvectortiles/__init__.py:__version__"]
tag_format = "v$version"
update_changelog_on_bump = true
major_version_zero = true
```

Rationale captured in the spec: adds the five imported-but-undeclared deps (`ipyleaflet`, `pmtiles`, `shapely`, `geopandas`, `mapbox-vector-tile`); drops never-imported `pydantic` and unused dev deps `flask`/`tomli`; fixes `readme`; discards the stale commitizen `version = "1.2.2"` (repo has no tags — `0.0.0` is the pre-release baseline and `pyvectortiles/__init__.py` already says `__version__ = "0.0.0"`, so the two version sources already agree).

- [ ] **Step 3: Verify the build now succeeds (green)**

```bash
rm -rf dist
.venv/bin/python -m build
.venv/bin/python -m zipfile -l dist/pyvectortiles-0.0.0-py3-none-any.whl | grep -E "client.py|__init__.py"
```

Expected: `Successfully built pyvectortiles-0.0.0.tar.gz and pyvectortiles-0.0.0-py3-none-any.whl`; the zipfile listing shows `pyvectortiles/client.py` and `pyvectortiles/__init__.py`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: switch to hatchling, fix readme, audit dependencies"
```

---

### Task 2: Replace the broken test script with CI-viable tests

**Files:**
- Create: `tests/test_smoke.py`
- Modify: `tests/test_range_request.py` (full replacement — currently a module-level script)

**Interfaces:**
- Consumes: installable package from Task 1 (`pip install -e '.[dev]'`).
- Produces: a pytest suite that is green in a clean env (`2 passed, 1 skipped`) — the gate used by Tasks 3, 4, and CI. Env var contract: `PYVECTORTILES_TEST_PMTILES`.

- [ ] **Step 1: Demonstrate the current suite cannot run (red)**

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

Expected: FAILURE during collection of `tests/test_range_request.py` — primary expectation `ModuleNotFoundError: No module named 'requests'`; also acceptable: a `TileClient` error about the hard-coded missing file `/home/dguerrero/1_modules/pyvectortiles/data/mbtiles/protomaps_firenze.pmtiles`. Either way: the suite cannot pass in any clean environment.

(Note: the `pip install -e '.[dev]'` pulls geopandas/shapely/ipyleaflet on Python 3.14 — expect ~1–3 min. If any dependency fails to resolve on 3.14, STOP and report; do not work around it.)

- [ ] **Step 2: Create `tests/test_smoke.py`:**

```python
"""Smoke tests: the package installs, imports, and exposes its entry point."""

import pyvectortiles


def test_version_is_set():
    assert isinstance(pyvectortiles.__version__, str)
    assert pyvectortiles.__version__


def test_tile_client_importable():
    from pyvectortiles.client import TileClient

    assert TileClient is not None
```

- [ ] **Step 3: Replace `tests/test_range_request.py` entirely with:**

```python
"""HTTP range-request behavior of the local tile server.

Needs a real PMTiles file; set PYVECTORTILES_TEST_PMTILES to its path to run:

    PYVECTORTILES_TEST_PMTILES=~/data/some.pmtiles pytest tests/test_range_request.py

Skipped otherwise (e.g. in CI).
"""

import os
from pathlib import Path

import httpx
import pytest

_PMTILES = os.environ.get("PYVECTORTILES_TEST_PMTILES", "")

pytestmark = pytest.mark.skipif(
    not (_PMTILES and Path(_PMTILES).expanduser().is_file()),
    reason="PYVECTORTILES_TEST_PMTILES not set to an existing .pmtiles file",
)


def test_range_request_returns_partial_content():
    from pyvectortiles.client import TileClient

    client = TileClient(str(Path(_PMTILES).expanduser()))
    layer = client.create_leaflet_layer()

    response = httpx.get(layer.url, headers={"range": "bytes=0-1023"})

    assert response.status_code == 206
    assert response.headers.get("content-range", "").startswith("bytes ")
    assert len(response.content) == 1024
```

Design notes for the implementer: the `TileClient` import lives *inside* the test so collection stays cheap when skipped; `httpx` replaces `requests` because it is already a runtime dependency; the three asserts pin the actual range-request contract (partial-content status, `Content-Range` header, exactly the 1024 requested bytes) instead of the old script's prints.

- [ ] **Step 4: Run the suite (green)**

```bash
.venv/bin/pytest -v
```

Expected: `2 passed, 1 skipped` — the skip reason shows `PYVECTORTILES_TEST_PMTILES not set to an existing .pmtiles file`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_smoke.py tests/test_range_request.py
git commit -m "test: replace range-request script with CI-viable pytest suite"
```

---

### Task 3: One-shot lint cleanup (ruff + black)

**Files:**
- Modify: most of `pyvectortiles/*.py` (mechanical; 9 of 12 files get reformatted), `tests/*.py` if touched

**Interfaces:**
- Consumes: `[tool.ruff]`/`[tool.black]` config from Task 1; green pytest gate from Task 2.
- Produces: `ruff check pyvectortiles tests` and `black --check pyvectortiles tests` both clean — the contract Task 4's lint session and CI enforce.

- [ ] **Step 1: Record the current violations (red)**

```bash
.venv/bin/ruff check pyvectortiles tests --statistics
.venv/bin/black --check pyvectortiles tests
```

Expected (verified 2026-07-16 with ruff 0.15.21 / black 26.5.1): **35 ruff errors** in `pyvectortiles/` — 10 RUF013 (implicit `Optional`), 9 I001 (import order), 8 F401 (unused imports), 5 E501 (long lines), 1 F541, 1 RUF010, 1 RUF019 — and black wanting to reformat 9 files. The Task-2 test files are already clean.

- [ ] **Step 2: Apply automatic fixes**

```bash
.venv/bin/ruff check pyvectortiles tests --fix --unsafe-fixes
.venv/bin/black pyvectortiles tests
```

`--unsafe-fixes` is required only for RUF013 (it rewrites `x: str = None` → `x: Optional[str] = None` and adds the import). Expected: `30 fixed, 5 remaining` from ruff, then black reformats 9 files.

- [ ] **Step 3: Manually rewrap the 5 remaining E501 lines (all strings/docstrings black won't split)**

Locate them with `.venv/bin/ruff check pyvectortiles --output-format concise`; expected positions after Step 2: `client.py:64`, `logger.py:23`, `styles.py:124-126`.

`pyvectortiles/client.py` (~line 64) — before:

```python
            raise ValueError(
                "PMTiles file is not available. Ensure that a valid data_source is provided or that the "
                "pmtiles_directory contains a PMTiles file."
            )
```

after:

```python
            raise ValueError(
                "PMTiles file is not available. Ensure that a valid data_source is "
                "provided or that the pmtiles_directory contains a PMTiles file."
            )
```

`pyvectortiles/logger.py` (~line 23) — before:

```python
        format_str = f"%(log_color)s%(asctime)s - {module_color}%(name)s{RESET} - %(levelname)s - %(message)s"
```

after (identical resulting string):

```python
        format_str = (
            f"%(log_color)s%(asctime)s - {module_color}%(name)s{RESET}"
            " - %(levelname)s - %(message)s"
        )
```

`pyvectortiles/styles.py` (~lines 124–126, docstring) — before:

```text
      categorized_field (str): The field name for categorization (required if style_mode is "categorized").
      categorized_values (list): List of distinct values for the field. Each value gets a random color.
      color_palette (str): Color palette to use. Options: 'vibrant', 'pastel', 'earth', 'cool', 'warm'
```

after (matches the continuation style already used by the `style_mode` entry two lines above):

```text
      categorized_field (str): The field name for categorization (required if
                               style_mode is "categorized").
      categorized_values (list): List of distinct values for the field. Each value
                                 gets a random color.
      color_palette (str): Color palette to use. Options: 'vibrant', 'pastel',
                           'earth', 'cool', 'warm'
```

- [ ] **Step 4: Verify lint is fully clean AND tests still pass (green)**

```bash
.venv/bin/ruff check pyvectortiles tests
.venv/bin/black --check pyvectortiles tests
.venv/bin/pytest
```

Expected: `All checks passed!`, `14 files would be left unchanged.` (12 package + 2 test files — zero reformats), and `2 passed, 1 skipped`. The pytest re-run guards against the F401 removals or RUF013 rewrites having broken imports at runtime.

- [ ] **Step 5: Commit**

```bash
git add pyvectortiles tests
git commit -m "style: apply ruff and black across the package"
```

---

### Task 4: Add `noxfile.py`

**Files:**
- Create: `noxfile.py`

**Interfaces:**
- Consumes: dev extras (Task 1), green pytest (Task 2), clean lint (Task 3).
- Produces: sessions `tests` (parametrized 3.10/3.11/3.12) and `lint` — the exact names Task 5's workflows invoke (`nox -s lint`, `nox -s tests -p <ver>`).

- [ ] **Step 1: Create `noxfile.py`:**

```python
import nox

PYTHON_VERSIONS = ["3.10", "3.11", "3.12"]


@nox.session(python=PYTHON_VERSIONS)
def tests(session: nox.Session) -> None:
    session.install("-e", ".[dev]")
    session.run("pytest", *session.posargs)


@nox.session(reuse_venv=True)
def lint(session: nox.Session) -> None:
    session.install("-e", ".[dev]")
    session.run("ruff", "check", "pyvectortiles", "tests")
    session.run("black", "--check", "pyvectortiles", "tests")
```

(Same shape as pysepal-api's noxfile minus its mypy/docs sessions; lint paths adapted to the flat layout.)

- [ ] **Step 2: Run the lint session (green)**

```bash
.venv/bin/nox -s lint
```

Expected: session `lint` ends with `Session lint was successful.` (it builds its own venv and installs `.[dev]` — allow a few minutes on first run).

- [ ] **Step 3: Confirm the tests sessions are wired (skips locally)**

```bash
.venv/bin/nox -s tests
```

Expected: each of `tests-3.10`, `tests-3.11`, `tests-3.12` is **skipped** with "Python interpreter 3.1x not found" — this machine only has 3.14. That is the expected local outcome; the matrix genuinely runs in CI (Task 6 verifies).

- [ ] **Step 4: Commit**

```bash
git add noxfile.py
git commit -m "build: add noxfile with lint and tests sessions"
```

---

### Task 5: Add the GitHub workflows

**Files:**
- Create: `.github/workflows/tests.yml`
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: nox session names from Task 4 (`lint`, `tests`), matrix values from Global Constraints.
- Produces: CI checks named `lint` and `tests (3.10|3.11|3.12)` (verified in Task 6); a release pipeline consumed by the Task 7 procedure.

- [ ] **Step 1: Create `.github/workflows/tests.yml`:**

```yaml
name: tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5
        with:
          python-version: "3.12"
      - run: python -m pip install nox
      - run: nox -s lint

  tests:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m pip install nox
      - run: nox -s tests -p ${{ matrix.python-version }}
```

- [ ] **Step 2: Create `.github/workflows/release.yml`:**

```yaml
name: Upload Python Package

on:
  release:
    types: [published]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write   # OIDC for trusted publishing to PyPI
      contents: read

    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4

      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5
        with:
          python-version: "3.12"

      - name: Install build tooling
        run: pip install build

      - name: Build distribution
        run: python -m build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b # v1.14.0
        # Auth via OIDC trusted publisher; no PYPI_PASSWORD needed.
```

(Byte-for-byte the pysepal-api release workflow.)

- [ ] **Step 3: Validate both files parse as YAML**

```bash
python3 -c "import yaml,sys; [yaml.safe_load(open(f)) for f in ['.github/workflows/tests.yml','.github/workflows/release.yml']]; print('YAML OK')"
```

Expected: `YAML OK` (system python3 has pyyaml).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/tests.yml .github/workflows/release.yml
git commit -m "ci: add tests and release workflows"
```

---

### Task 6: Push, open PR, verify CI is green

**Files:** none (git/GitHub operations only)

**Interfaces:**
- Consumes: all previous commits on `ci/release-workflows`.
- Produces: a merged-ready PR with 4 green checks: `lint`, `tests (3.10)`, `tests (3.11)`, `tests (3.12)`.

- [ ] **Step 1: Push the branch**

```bash
git push -u origin ci/release-workflows
```

- [ ] **Step 2: Open the PR** (plain body — per Global Constraints, no generated-with/co-author footer)

```bash
gh pr create --title "Add CI and release workflows" --body "Ports the pysepal-api setup: lint+tests workflows (nox, py3.10-3.12) and PyPI trusted-publishing release workflow. Fixes packaging (hatchling, readme, dependency audit) and makes the test suite CI-viable. Spec: docs/superpowers/specs/2026-07-16-ci-release-workflows-design.md"
```

- [ ] **Step 3: Watch the checks**

```bash
gh pr checks --watch
```

Expected: all 4 checks pass (`lint`, `tests (3.10)`, `tests (3.11)`, `tests (3.12)`). The tests jobs each report `2 passed, 1 skipped` inside their logs.

- [ ] **Step 4: If any check fails** — read `gh run view --log-failed`, fix on this branch, commit with a conventional message, push, and re-watch. Do NOT merge with red checks. (No commit here if everything is green.)

---

### Task 7: One-time release setup + first release (user actions)

**Files:** none (browser + release commands). This task is for the user; the agent's job is to present it and, post-merge, run Step 3 on request.

- [ ] **Step 1 (browser): Register the PyPI pending trusted publisher**

At <https://pypi.org/manage/account/publishing/> → "Add a new pending publisher" (GitHub tab):
- PyPI project name: `pyvectortiles`
- Owner: `dfguerrerom`
- Repository name: `ipy-pmtiles`
- Workflow name: `release.yml`
- Environment name: `pypi`

("Pending" publishers exist precisely so this can be configured before the project's first upload.)

- [ ] **Step 2 (browser): Create the GitHub environment**

At <https://github.com/dfguerrerom/ipy-pmtiles/settings/environments> → "New environment" → name it exactly `pypi`. No secrets needed. Optionally add a deployment-branch/tag rule restricting it to tags matching `v*`.

- [ ] **Step 3 (terminal, after the PR is merged): First release**

```bash
git checkout main && git pull
.venv/bin/cz bump          # computes 0.1.0 from the feat commits, updates pyproject + __init__ + CHANGELOG.md, commits, tags v0.1.0
git push --follow-tags
gh release create v0.1.0 --generate-notes
```

Publishing the release fires `release.yml` → build → PyPI. Verify with:

```bash
gh run watch
.venv/bin/pip index versions pyvectortiles
```

Expected: the workflow's `deploy` job succeeds and PyPI reports `pyvectortiles (0.1.0)`.

Note: the first `cz bump` generates `CHANGELOG.md` from the whole conventional-commit history; non-conventional commits ("Update README.md") are simply ignored.
