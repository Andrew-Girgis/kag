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
  - `data/` (download + extract) with `data/SCHEMA.md` describing each file's columns
  - `<competition>.ipynb`
  - `notes.md` (overview, evaluation, data description, rules, and top notebooks from Kaggle)
  - `AGENTS.md` and `CLAUDE.md` so coding agents start with the metric, submission format, and limits
  - `.kag/competition.json` (machine-readable competition metadata)
  - `.venv` (optional)
  - `git init` (optional)
- Checks competition access before download and opens browser tabs for `overview` + `rules` when acceptance is needed.
- Fills `notes.md` from Kaggle's official competition pages (`Overview`, `Evaluation`, `Data`, `Code`, `Rules`).

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

Maintainer release planning lives in [`docs/release.md`](docs/release.md).

## Setup guide

### 1. Install kag

```bash
uv tool install kag
```

### 2. Sign in to Kaggle

kag installs the Kaggle CLI and library for you (Python 3.11+); there is nothing else to install. Sign in once in your browser:

```bash
kag login
```

This runs the Kaggle CLI bundled with kag (`kaggle auth login`) and caches credentials in `~/.kaggle/`. Other ways to authenticate also work:
- API token: `KAGGLE_API_TOKEN`, or the token saved to `~/.kaggle/access_token`
- Legacy: `KAGGLE_USERNAME` + `KAGGLE_KEY`, or `~/.kaggle/kaggle.json` containing `username` and `key`

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
kag new titanic      # create a workspace without the TUI
kag login            # sign in to Kaggle (first time only)
kag --doctor         # environment checks
kag --version        # show installed version
kag --help           # show CLI help
```

## Usage

```bash
kag                  # open TUI
kag titanic          # open TUI with initial search query
kag --doctor         # environment checks
kag --doctor --json  # machine-readable checks
kag --version        # show installed version
kag --init           # print optional shell integration
kag --help           # show CLI help
```

`kag --help` prints usage information without requiring Kaggle CLI authentication.

## For scripts and AI agents: `kag new`

`kag new` builds the same workspace as the TUI without any prompts, which makes it usable from scripts and coding agents:

```bash
kag new titanic --json                  # create ~/Kaggle/titanic and print a JSON result
kag new titanic --json --no-download    # metadata, notes, and agent files only
kag new titanic --json --force          # existing folder: add missing files (never overwrites)
```

Options: `--no-download`, `--no-git`, `--no-venv`, `--editor NAME`, `--force`, `--json`. Progress goes to stderr; the result goes to stdout.

| Status | Exit code | Meaning |
|---|---|---|
| `created` / `updated` | 0 | Workspace ready. `next_steps` says where to start (`AGENTS.md`). |
| `error` | 1 | Something failed; see `message`. |
| `needs_join` | 3 | Join the competition and accept its rules at `url` (a human has to click), then rerun. |
| `exists` | 4 | The folder already exists; rerun with `--force` to add missing files. |
| `cancelled` | 130 | Interrupted with Ctrl-C; changes were rolled back. |

Every project includes `AGENTS.md` (plus a `CLAUDE.md` that imports it) and `.kag/competition.json`, so an agent starts with the metric, submission template, and daily submission limit. When data is downloaded, `data/SCHEMA.md` (kept local with the data, not committed) adds per-file column schemas; with `--no-download`, `files.schema` is `null` until a later `kag new --force` downloads the data.

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
- bundled Kaggle CLI + auth status
- API probe (`kaggle competitions list --page-size 1`)
- shell hook presence
- writable directories
- detected editors

If you pick Jupyter Lab (or another editor) when creating a project, its output is written to `.kag/logs/<editor>.log` inside the project. On a headless or SSH session, find the Jupyter server URL and token there, or run `jupyter server list`.

## Current limitations

- Competition join/terms acceptance is browser-assisted (not a direct Kaggle CLI command).
- Notes extraction depends on Kaggle page APIs/content shape and may vary by competition.
- Search is substring-based (not fuzzy-ranked yet).

## License

MIT
