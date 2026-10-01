<!-- sdlc stage=intent model=glm-5.3:cloud from=idea@3c77666 -->
# Intent: Migrate Python dependency management to uv

**Owner:** @ly2xxx · **Status:** proposed (approving the review gate approves it)

## Problem
The project pins its Python dependencies in a `requirements.txt` with loose lower bounds and no lockfile, so developers and CI resolve different package versions over time. This makes builds non-reproducible and lets dependency drift produce failures ("works on my machine", flaky CI) that cost debugging time for anyone contributing to the `app` package or reviewing CI results.

## Outcome
Dependency management for the Python code uses uv: a `pyproject.toml` declares the project and its dependencies, a committed `uv.lock` pins them reproducibly, and `requirements.txt` is retired. CI installs dependencies and runs the tests (`app/tests/`, `scripts/tests/`) through uv, so every environment gets the same resolved versions.

## Done when
- A `pyproject.toml` exists declaring the project and the dependencies currently listed in `requirements.txt` (fastapi, httpx, numpy, pyyaml).
- A `uv.lock` is committed and pins those dependencies reproducibly.
- CI installs dependencies and runs the test suite using uv commands.
- `requirements.txt` is no longer used by the project's workflow; installing via `uv sync` (or equivalent) yields a working environment.
- The existing tests still pass.

## Not in scope
- Changing any application code in `app/` or the Helm/Kubernetes manifests.
- Updating or adding dependencies beyond what `requirements.txt` already lists.
- Changes to deployment tooling outside CI (Helm charts, k8s manifests, PowerShell scripts).
- Adopting uv features beyond dependency resolution and test execution (e.g., publishing, workspaces).

## Open questions
- Should `requirements.txt` be deleted or kept temporarily as a compatibility artifact? Assumption: it is deleted, since uv replaces it.
- Which Python version should be pinned in `pyproject.toml`? Assumption: whatever CI currently uses, with no new version constraint invented.
- Should the `scripts/tests/` suites also run through uv in CI? Assumption: yes, if CI already runs them; otherwise only `app/tests/`.
- No existing intent.md for this change was provided (the one under `sdlc/features/001` belongs to a different feature), so this is a fresh document rather than a revision.
