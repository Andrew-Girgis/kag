# kag - fresh Kaggle competition workspaces from your terminal

`kag` is a Textual TUI inspired by [`try`](https://github.com/tobi/try), built for Kaggle workflows.

It helps you go from "I want to work on this competition" to a ready folder with data, notebook, notes, and editor open.

## Demo

Asciinema walkthrough placeholder: `docs/demo-placeholder.md`

Planned recording file path: `docs/demo.cast`

## What kag does

- Shows a searchable competition picker with sections:
  - `Your notebooks` (local projects in `KAG_PATH`)
  - `Joined competitions`
  - `All competitions`
- Uses paginated loading for competitions (`20` per page) and auto-loads more when you reach the end.
- Scaffolds a project folder:
  - `data/` (download + extract)
  - `<competition>.ipynb`
  - `notes.md`
  - `.venv` (optional)
  - `git init` (optional)
- Checks competition access before download and opens browser tabs for `overview` + `rules` when acceptance is needed.
- Enriches `notes.md` from Kaggle competition content (`Overview`, `Evaluation`, `Data`, `Code`, `Rules`).

## Installation

### Prerequisites

- Python 3.11+
- [Kaggle CLI](https://github.com/Kaggle/kaggle-api) installed and authenticated
  - Preferred: `KAGGLE_API_TOKEN`
  - Also supported: `KAGGLE_USERNAME` + `KAGGLE_KEY`
  - Legacy fallback: `~/.kaggle/kaggle.json`

### Install with uv

```bash
uv tool install .
```

For development:

```bash
uv sync
```

## Shell integration (for automatic cd)

Add this to your shell config:

```bash
# zsh/bash
eval "$(kag --init)"
```

Without shell integration, `kag` still works, but your current shell will not auto-`cd` into the selected project directory.

## Usage

```bash
kag                  # open TUI
kag titanic          # open TUI with initial search query
kag --doctor         # environment checks
kag --doctor --json  # machine-readable checks
```

## How it works

1. Open picker (`kag`)
2. Search and select competition or local project
3. If needed, choose download and editor
4. `kag` verifies competition access before download
5. Project is scaffolded and opened
6. If `--init` hook is installed, your shell `cd`s into the project

## Search behavior

Search is currently case-insensitive substring filtering over competition slug/title and local project names.

## Configuration

`KAG_PATH` controls where projects are created (default: `~/Kaggle`):

```bash
export KAG_PATH=~/Kaggle
```

Optional `~/.kag_config.toml`:

```toml
kag_path = "/Users/you/Kaggle"
default_editor = "code"
auto_venv = true
auto_git = true
```

## Troubleshooting

Run:

```bash
kag --doctor
```

It checks:

- `kag` on PATH
- `kaggle` CLI + auth status
- API probe (`kaggle competitions list --page-size 1`)
- shell hook presence
- writable directories
- detected editors

## Current limitations

- Competition join/terms acceptance is browser-assisted (not a direct Kaggle CLI command).
- Notes extraction depends on Kaggle page APIs/content shape and may vary by competition.
- Search is substring-based (not fuzzy-ranked yet).

## License

MIT
