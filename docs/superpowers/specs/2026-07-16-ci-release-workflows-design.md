# CI/Release Workflows — Design

**Date:** 2026-07-16
**Status:** Approved
**Repo:** `dfguerrerom/ipy-pmtiles` · **PyPI project:** `pyvectortiles` · **Import:** `pyvectortiles`

## Goal

Port the CI and release setup from `pysepal-api` so this project gets: lint + test checks
on every push/PR, and automated PyPI publishing (OIDC trusted publishing, no tokens) when
a GitHub Release is published. Fix the packaging problems that currently make any release
impossible.

## Decisions

| Topic | Decision |
|---|---|
| PyPI / import name | `pyvectortiles` for both. Repo name (`ipy-pmtiles`) differs — accepted, cosmetic. |
| Layout | Keep flat `pyvectortiles/` package. No rename, no `src/` move. |
| CI scope | `lint` + `tests` jobs only. No mypy (codebase not typed to standard), no docs workflow. |
| Build backend | `hatchling` (parity with pysepal-api; also fixes the current broken build). |
| Versioning | commitizen, `version_provider = "pep621"`. Baseline `0.0.0`; first `cz bump` computes `0.1.0` from conventional-commit history. The stale `1.2.2` in the old commitizen section is discarded (repo has no tags). |
| Python support | `requires-python = ">=3.10"`; CI matrix 3.10 / 3.11 / 3.12. |
| Lint tooling | ruff (`E,F,W,I,RUF`) + black, line-length 100 — same as pysepal-api. Deprecated ruff keys removed. |

## Deliverables

### 1. `.github/workflows/tests.yml`

Ported from pysepal-api minus the mypy job. Triggers: push to `main`, all PRs.

- **lint** job: `pip install nox` → `nox -s lint`
- **tests** job: matrix `["3.10", "3.11", "3.12"]`, `fail-fast: false` → `nox -s tests -p <ver>`
- Actions pinned by SHA (same pins as pysepal-api):
  - `actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5` (v4)
  - `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065` (v5)

### 2. `.github/workflows/release.yml`

Verbatim port. Triggers: `release: [published]` + `workflow_dispatch`.
Single `deploy` job: `environment: pypi`, permissions `id-token: write` / `contents: read`,
checkout → setup-python 3.12 → `pip install build` → `python -m build` → publish with
`pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b` (v1.14.0).
Auth via OIDC trusted publisher — no secrets.

### 3. `noxfile.py`

Mirror of pysepal-api's, minus mypy/docs sessions, paths adapted:

- `tests` (python 3.10–3.12): `session.install("-e", ".[dev]")` → `pytest`
- `lint` (reuse_venv): `ruff check pyvectortiles tests` + `black --check pyvectortiles tests`

### 4. `pyproject.toml` rewrite

Modeled on pysepal-api's. Changes from current file:

- **Build system:** `hatchling>=1.18` with `[tool.hatch.build.targets.wheel] packages = ["pyvectortiles"]`.
- **Metadata:** `readme = "README.md"` (current file declares `README.rst`, which does not
  exist — this breaks `python -m build` today); `license = "MIT"`; `version = "0.0.0"`;
  description kept; classifiers updated to Python 3.10–3.12; URLs → Homepage/Repository
  `https://github.com/dfguerrerom/ipy-pmtiles`.
- **Dependency audit** (derived from actual imports):
  - Keep: `starlette`, `uvicorn`, `httpx`, `colorlog`
  - Add (imported but undeclared): `ipyleaflet`, `pmtiles`, `shapely`, `geopandas`, `mapbox-vector-tile`
  - Drop (declared but never imported): `pydantic`
- **dev extras:** `pytest`, `ruff`, `black`, `nox`, `commitizen`, `pre-commit`
  (drops unused `flask`, `tomli`).
- **Tool config:** `[tool.black]` + `[tool.ruff]` line-length 100, `[tool.ruff.lint]
  select = ["E","F","W","I","RUF"]` (replaces the deprecated top-level ruff keys);
  `[tool.pytest.ini_options] testpaths = ["tests"]`; `[tool.coverage.run]` dropped
  (nothing runs coverage; re-add with a coverage session if wanted later).
- **Commitizen:**

  ```toml
  [tool.commitizen]
  name = "cz_conventional_commits"
  version_provider = "pep621"
  version_files = ["pyvectortiles/__init__.py:__version__"]
  tag_format = "v$version"
  update_changelog_on_bump = true
  major_version_zero = true
  ```

### 5. Tests made CI-viable

The current `tests/test_range_request.py` is a module-level script (no assertions,
hard-coded local path, imports `requests` which is not a dependency) — it fails pytest
collection. Replace with:

- `tests/test_smoke.py`: import `pyvectortiles`, assert `__version__` is a string; import
  `TileClient`. Runs everywhere — verifies the package installs and its dependencies are
  fully declared in a clean venv.
- `tests/test_range_request.py`: the same flow as a real test function using `httpx`
  (already a dependency), asserting status 206 and `Content-Range` presence. Skipped via
  `pytest.mark.skipif` unless env var `PYVECTORTILES_TEST_PMTILES` points to an existing
  `.pmtiles` file. CI skips it; locally run with the env var set.

### 6. One-time lint cleanup commit

Run `ruff check --fix` and `black .` across the codebase once so the lint job is green
from the first CI run. Mechanical, isolated in its own commit.

### 7. `pyvectortiles/__init__.py`

Only guaranteed change: none needed for the name (already `pyvectortiles`, version already
`0.0.0`, matching the pyproject baseline). It stays the commitizen version_file target.

## Release process (day-to-day)

1. Merge work to `main` with conventional commits.
2. `cz bump` — bumps `pyproject.toml` + `__init__.py`, regenerates `CHANGELOG.md`, commits, tags `vX.Y.Z`.
3. `git push --follow-tags`
4. `gh release create vX.Y.Z --generate-notes` (or via web UI).
5. `release.yml` fires on the published release → builds → publishes to PyPI.

Note: the first `cz bump` generates `CHANGELOG.md` from the full history; non-conventional
commits (e.g. "Update README.md") are ignored by commitizen.

## One-time manual setup (user, in browser)

1. **PyPI pending trusted publisher** — pypi.org → Account → Publishing → "Add a new
   pending publisher": project `pyvectortiles`, owner `dfguerrerom`, repository
   `ipy-pmtiles`, workflow `release.yml`, environment `pypi`. (Pending publishers allow
   registering before the project's first upload.)
2. **GitHub environment** — repo Settings → Environments → create `pypi`
   (optionally restrict deployments to tags).

## Verification

- `nox -s lint` and `nox -s tests` pass locally.
- `python -m build` produces sdist + wheel without errors (currently impossible — README.rst bug).
- Push branch, open PR → `tests.yml` runs green on all matrix entries.
- Release dry-run is implicitly covered by the first real release (`0.1.0`).

## Out of scope

- mypy job (would require annotating the codebase first)
- docs workflow / mkdocs site
- `.pre-commit-config.yaml` (commitizen + pre-commit stay in dev extras for later)
- Writing further tests beyond the smoke + range-request pair
- Renaming the GitHub repo to match the package (user may do later; GitHub redirects)
