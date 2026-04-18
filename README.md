# kag - fresh directories for every kaggle competition

*Heavily inspired by Tobi's brilliant [try](https://github.com/tobi/try) - but built for data science.*

Setup should take seconds, not twenty minutes. 🏠

For everyone who constantly creates new folders for their Kaggle Competition notebooks, a terminal app to quickly manage, download, and navigate to keep them somewhat organized.

Ever find yourself with 50 directories named `titanic`, `titanic2`, `new-titanic`, `actually-working-titanic`, scattered across your filesystem? Or worse, manually unzipping data and typing out `import pandas as pd` for the 100th time?

`kag` is here for your beautifully chaotic data mind.

## The Problem
You're learning XGBoost. You create `~/Desktop/titanic`. You run `kaggle competitions download -c titanic`. You unzip it. You create a virtual environment. You touch `titanic.ipynb`. You write the pandas imports. Twenty minutes later, you're finally looking at the data, but your 2am motivation is entirely gone.

## The Solution
All your competitions in one place, with an instant fuzzy search TUI:

```bash
$ kag
```

Type, arrow down, enter. You're there. The data is downloaded, the environment is ready, and your editor is open.

## What it does

Instantly navigate through your Kaggle projects and bootstrap new competitions with:

* **Interactive TUI** - Browse your existing projects or the entire Kaggle catalog
* **Instant Scaffolding** - Downloads data, creates a starter notebook, sets up git, and builds a venv
* **Zero friction** - Just type to search, hit enter, and you're coding

## Installation

### Prerequisites
- Python 3.11+
- [Kaggle CLI](https://github.com/Kaggle/kaggle-api) installed and authenticated (`~/.kaggle/kaggle.json`)

### uv (Recommended)

```bash
uv tool install .
```
*(or `uv sync` for development)*

Then add the shell hook so `kag` can automatically `cd` you into your new projects:

```bash
# Bash/Zsh - add to .zshrc or .bashrc
eval "$(kag init)"

# Fish - add to config.fish
kag init | source
```

## Features

**Smart Scaffolding**
Not just downloading a zip. `kag` builds a real project:
```text
~/Kaggle/titanic/
├── data/             # Extracted competition files
├── titanic.ipynb     # Starter notebook with imports & data loading
├── notes.md          # Competition metadata & notes template
├── .gitignore
└── .venv/            # Ready-to-use Python virtual environment
```

**TUI**
Clean, minimal terminal interface powered by Textual.
Highlights matches as you type. Dark mode by default (because obviously).

**Instant Editor Launch**
Automatically boots up your environment in:
- VS Code (`code`)
- Cursor
- Zed
- Windsurf
- Jupyter Lab

**Stay Organized**
Everything lives in `~/Kaggle` (configurable via `KAG_PATH`).

## Configuration
Set `KAG_PATH` to change where experiments are stored:

```bash
export KAG_PATH=~/projects/data-science
```
Default: `~/Kaggle`

Or create a `~/.kag_config.toml` for more control:
```toml
kag_path = "/Users/you/Kaggle"
default_editor = "cursor"
auto_venv = true
auto_git = true
```

## Usage
```bash
kag                  # Open the TUI to browse or create
kag --help           # Show help
```

### Keyboard Shortcuts
- `↑/↓` or `j/k` - Navigate
- `Enter` - Select or create
- `ESC` or `Ctrl+C` - Cancel
- `q` - Quit
- Just type to filter

## License

MIT - Do whatever you want with it.

Skip to the fun part - exploring the data 
