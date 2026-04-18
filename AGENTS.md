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

## Commands
- `uv run python -m kag.cli` - Run the app locally
- `uv run ruff check src/` - Lint
- `uv run ruff format src/` - Format
- `uv run pytest` - Run tests

## External Dependencies
- `kaggle` CLI must be installed and authenticated on the user's system
- Check for it at startup with a clear error message if missing