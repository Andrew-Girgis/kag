# Release Process

This document describes how maintainers release `kag` to TestPyPI and PyPI.

## Goals

- Publish `kag` from GitHub after release checks pass.
- Keep release publishing separate from normal pull request CI.
- Prevent feature branches and ordinary pushes from publishing packages.
- Use PyPI trusted publishing instead of long-lived API tokens.
- Validate on TestPyPI before publishing the real PyPI release.

## Current Release Workflow

Release automation lives in `.github/workflows/release.yml`.

The workflow has three jobs:

- `build`: validates and builds the package.
- `publish-testpypi`: publishes to TestPyPI from a manual workflow dispatch on `main`.
- `publish-pypi`: publishes to PyPI from a pushed version tag like `v0.1.1`.

Normal pull requests, feature branch pushes, and ordinary `main` pushes do not publish packages. The `build` job fails if the commit being released is not on `main`, so a tag pushed from an unmerged branch cannot publish.

## Required Release Checks

Before publishing, the workflow runs:

```bash
uv sync --locked
uv run ruff check src/ tests/
uv run pytest
uv build
uvx twine check --strict dist/*
```

It also verifies:

- the release commit is on `main`.
- `pyproject.toml` version matches `src/kag/__init__.py`.
- tag releases use a tag that matches the package version, such as `v0.1.1` for version `0.1.1`.

If any check fails, publishing stops.

## Trusted Publishing Setup

Before using the release workflow, configure trusted publishing in TestPyPI and PyPI.

### GitHub Environments

The repository has these GitHub environments (Settings -> Environments):

- `testpypi`: deployments allowed only from the `main` branch. No approval required.
- `pypi`: deployments allowed only from `v*` tags. Requires maintainer approval before publishing.

Together with the `build` job's `main` check, a release needs a commit on `main`, a matching version tag, and an explicit approval.

### TestPyPI Publisher

Configure a trusted publisher for the TestPyPI `kag` project:

- Publisher: GitHub
- Repository owner: `Andrew-Girgis`
- Repository name: `kag`
- Workflow name: `release.yml`
- Environment name: `testpypi`

### PyPI Publisher

Configure a trusted publisher for the PyPI `kag` project:

- Publisher: GitHub
- Repository owner: `Andrew-Girgis`
- Repository name: `kag`
- Workflow name: `release.yml`
- Environment name: `pypi`

The environment names must match the workflow jobs. A mismatch causes PyPI trusted publishing to reject the upload.

## TestPyPI Release Rehearsal

Use TestPyPI to validate packaging before the real release.

1. Create and merge a release-prep PR with a unique test version, such as `0.1.1rc1` or `0.1.1.dev1`.
2. Open GitHub Actions.
3. Select the `Release` workflow.
4. Run the workflow manually from the `main` branch with `target=testpypi`.
5. Wait for the `build` and `publish-testpypi` jobs to pass.
6. Smoke test the exact wheel uploaded to TestPyPI in an isolated environment:

   ```bash
   VERSION=0.1.1rc1
   WHEEL_URL=$(curl -fsSL "https://test.pypi.org/pypi/kag/$VERSION/json" \
     | python3 -c 'import json,sys; print(next(f["url"] for f in json.load(sys.stdin)["urls"] if f["packagetype"] == "bdist_wheel"))')

   uvx --isolated --from "kag @ $WHEEL_URL" kag --version
   uvx --isolated --from "kag @ $WHEEL_URL" kag --help
   uvx --isolated --from "kag @ $WHEEL_URL" kag --doctor
   ```

   This installs `kag` from TestPyPI and all dependencies from real PyPI, without touching an installed `kag`. Avoid `--index-url`/`--extra-index-url` mixes: `kag` also exists on PyPI, so uv may resolve the old production release instead of the rehearsal build, and TestPyPI copies of dependencies are not trustworthy.

PyPI and TestPyPI versions are immutable. If a TestPyPI rehearsal needs to be repeated, use a new unique prerelease/dev version.

## PyPI Release

1. Create and merge a final release-prep PR with the final version in both:

   - `pyproject.toml`
   - `src/kag/__init__.py`

2. Confirm `main` is green in CI.
3. Create and push a matching tag:

   ```bash
   git tag v0.1.1
   git push origin v0.1.1
   ```

4. The `Release` workflow runs automatically.
5. The workflow validates, builds, and publishes to PyPI through the `pypi` environment.
6. Approve the `pypi` deployment in GitHub when prompted.
7. Create a GitHub Release from the tag with release notes.
8. Verify the published package:

   ```bash
   uvx --isolated kag@0.1.1 --version
   uvx --isolated kag@0.1.1 --help
   ```

## Manual Fallback

GitHub trusted publishing is the normal release path. Only use local publishing as a fallback if the GitHub workflow is unavailable.

If local publishing is required, still run checks first:

```bash
uv sync --locked
uv run ruff check src/ tests/
uv run pytest
uv build
uvx twine check --strict dist/*
```

Do not store PyPI credentials in the repository.
