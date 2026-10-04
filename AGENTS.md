# AGENTS.md - Project conventions for AI-assisted development

## Tech Stack
- Python 3.11+
- [Textual](https://textual.textualize.io/) for TUI framework
- [Rich](https://rich.readthedocs.io/) for terminal formatting
- `uv` for package management
- `kaggle` CLI (external dependency, must be pre-installed by user)

## Project Structure
- `src/kag/` - Main package
- `src/kag/screens/` - Textual screen classes
- `src/kag/templates/` - Starter notebook and file templates
- `tests/` - Tests

## Code Style
- Use type hints everywhere
- No comments unless explicitly asked
- 4-space indentation
- Use `from __future__ import annotations` for modern type hints if needed
- Dataclasses for structured data (see `kaggle_api.py`)
- Each screen is a separate file in `screens/`

## Key Patterns
- Screens communicate via custom message classes (e.g., `CompetitionListScreen.Selected`)
- Shell cd integration via `kag init` (prints shell function, like `try`)
- Kaggle API calls are wrapped in `@work` async workers to avoid blocking TUI
- Config loaded from `~/.kag_config.toml` with env var overrides

## GitHub Workflow
- Use issue-first development for public repo work.
- When adding a TODO/backlog feature, create or identify a matching GitHub issue.
- Before starting implementation, make sure there is a GitHub issue for the work; if there is not, create one first.
- Create a feature/fix branch for each issue before coding.
- Do not implement fixes directly on `main`; switch to a dedicated issue branch first, such as `fix/<issue>-short-description`.
- Include the issue number in branch names where practical, such as `fix/12-offline-kaggle-error` or `feature/15-loading-animation`.
- Link pull requests to their GitHub issue.
- Prefer small, focused PRs that map to one issue.
- Run tests and lint locally before opening a PR when feasible.
- Merge through pull requests after automated checks pass.
- Do not publish releases from feature branches.

## Commands
- `uv run python -m kag.cli` - Run the app locally
- `uv run ruff check src/ tests/` - Lint
- `uv run ruff format src/ tests/` - Format
- `uv run pytest` - Run tests

## External Dependencies
- `kaggle` CLI must be installed and authenticated on the user's system
- Check for it at startup with a clear error message if missing
