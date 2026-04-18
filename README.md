# kag - Kaggle Competition Bootstrapper

A TUI tool to quickly bootstrap Kaggle competition projects. Inspired by [try](https://github.com/tobi/try).

## What it does

```
$ kag
```

Opens an interactive terminal UI where you can:
- Browse your existing Kaggle projects
- List and search Kaggle competitions
- Download competition files
- Create a structured project directory with starter notebook, notes, git, and venv
- Open in your preferred editor

No manual setup required - get right into the data.

## Installation

### Prerequisites

- Python 3.11+
- [Kaggle CLI](https://github.com/Kaggle/kaggle-api) installed and authenticated
- `~/.kaggle/kaggle.json` configured

### Install with uv (recommended)

```bash
uv tool install .
```

Or for development:

```bash
uv sync
```

### Shell integration

Add to your `.zshrc` or `.bashrc`:

```bash
eval "$(kag init)"
```

This enables the `kag` shell function that can change your working directory after selecting a competition.

### Configuration

Set `KAG_PATH` to change where projects are stored (default: `~/Kaggle`):

```bash
export KAG_PATH=~/my-kaggle-projects
```

Or create `~/.kag_config.toml`:

```toml
kag_path = "/Users/you/Kaggle"
default_editor = "code"
auto_venv = true
auto_git = true
```

## Usage

```bash
kag                  # Open the TUI
kag init             # Print shell wrapper for cd integration
```

### Keyboard shortcuts

- `↑/↓` or `j/k` - Navigate
- `Enter` - Select
- Type to filter/search
- `Esc` - Cancel/Go back
- `q` - Quit

## What gets created

For a competition like `titanic`, running `kag` creates:

```
~/Kaggle/titanic/
├── data/             # Downloaded competition files
├── titanic.ipynb     # Starter notebook with imports & data loading
├── notes.md          # Competition metadata & notes template
├── .gitignore
└── .venv/            # Python virtual environment
```

## Supported editors

- VS Code (`code`)
- Cursor
- Zed
- Windsurf
- Jupyter Lab
- Terminal only (no editor launched)

## License

MIT