# kag - fresh Kaggle competition workspaces from your terminal

[![PyPI](https://img.shields.io/pypi/v/kag.svg)](https://pypi.org/project/kag/)
[![Python Versions](https://img.shields.io/pypi/pyversions/kag.svg)](https://pypi.org/project/kag/)

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

`kag` is published on PyPI and installs as a global terminal command.

### Recommended: uv

```bash
uv tool install kag
```

### Alternative: pipx

```bash
pipx install kag
```

### Fallback: pip

```bash
python -m pip install kag
```

Validate your install:

```bash
kag --version
kag --doctor
```

For development from this repository:

```bash
uv sync
uv run kag --doctor
```

## Setup guide

### 1. Install kag

```bash
uv tool install kag
```

### 2. Install and authenticate Kaggle CLI

- Python 3.11+
- [Kaggle CLI](https://github.com/Kaggle/kaggle-api) installed and authenticated
  - Preferred: `KAGGLE_API_TOKEN`
  - Also supported: `KAGGLE_USERNAME` + `KAGGLE_KEY`
  - Legacy fallback: `~/.kaggle/kaggle.json`

```bash
python -m pip install kaggle
kaggle --version
```

### 3. Verify your environment

```bash
kag --doctor
```

Fix any `FAIL` rows before starting a competition workspace.

### 4. Choose where projects are created

By default, `kag` creates projects in `~/Kaggle`. Override it with `KAG_PATH`:

```bash
export KAG_PATH=~/Kaggle
```

Optional persistent config lives at `~/.kag_config.toml`:

```toml
kag_path = "/Users/you/Kaggle"
default_editor = "code"
auto_venv = true
auto_git = true
```

### 5. Start using kag

```bash
kag
kag titanic
```

Optional shell integration lets `kag` automatically `cd` into the selected project directory:

```bash
eval "$(kag --init)"
```

## Quick start

```bash
kag                  # open TUI
kag titanic          # open TUI with initial search query
kag --doctor         # environment checks
kag --version        # show installed version
```

## Usage

```bash
kag                  # open TUI
kag titanic          # open TUI with initial search query
kag --doctor         # environment checks
kag --doctor --json  # machine-readable checks
kag --version        # show installed version
kag --init           # print optional shell integration
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
