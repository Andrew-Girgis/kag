# Release Plan

This document describes the planned PyPI release workflow for maintainers. It is a CD plan, not an active publishing workflow yet.

## Goals

- Publish `kag` from GitHub only after CI is stable.
- Keep release publishing separate from normal pull request checks.
- Prevent feature branches and arbitrary pushes from publishing packages.
- Prefer PyPI trusted publishing over long-lived API tokens.
- Make every release reproducible from a Git tag.

## Current State

- Pull request and `main` checks run in GitHub Actions.
- The package metadata lives in `pyproject.toml`.
- The package is built with Hatchling through `uv build`.
- Publishing is still manual until the CD workflow is added.

## Planned Trigger

Publishing should only run for intentional release events:

- Preferred: pushing a version tag like `v0.1.1`.
- Optional later: a manual `workflow_dispatch` release workflow that requires a version input.

The release workflow should not run for feature branches or normal pull requests.

## Required Release Checks

Before publishing, the release workflow should run:

```bash
uv sync --locked
uv run ruff check src/ tests/
uv run pytest
uv build
```

If any check fails, publishing should stop.

## Planned GitHub Actions Shape

The future workflow should be separate from CI, for example `.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      contents: read
      id-token: write

    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - run: uv python install 3.11
      - run: uv sync --locked
      - run: uv run ruff check src/ tests/
      - run: uv run pytest
      - run: uv build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

## PyPI Trusted Publishing Setup

Before enabling the release workflow, configure PyPI trusted publishing for this repository:

- Repository owner: `Andrew-Girgis`
- Repository name: `kag`
- Workflow name: `release.yml`
- Environment name: optional, such as `pypi`

If trusted publishing is not available, use a GitHub environment secret for a PyPI API token as a fallback. Do not publish from a developer machine using local credentials as the normal release process.

## Manual Release Checklist

Until CD is implemented, use this checklist for releases:

1. Confirm `main` is green in CI.
2. Update `version` in `pyproject.toml`.
3. Update release notes.
4. Run local checks:

   ```bash
   uv sync --locked
   uv run ruff check src/ tests/
   uv run pytest
   uv build
   ```

5. Commit the version bump.
6. Tag the release, for example `v0.1.1`.
7. Publish to PyPI.
8. Create a GitHub release from the tag.

## Future CD Acceptance Criteria

- Release publishing runs only on intentional release tags or approved manual dispatches.
- The workflow runs lint, tests, and build before publishing.
- PyPI publishing uses trusted publishing or protected repository secrets.
- Failed checks prevent publishing.
- Normal pull requests and feature branch pushes cannot publish packages.
