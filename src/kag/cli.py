import os
import sys
import shutil
import subprocess
from pathlib import Path

from .config import Config


def check_kaggle_cli() -> str | None:
    kaggle_path = shutil.which("kaggle")
    if not kaggle_path:
        return "kaggle CLI not found. Install with: pip install kaggle"
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if not kaggle_json.exists():
        return (
            f"kaggle credentials not found at {kaggle_json}.\n"
            "Run: kaggle config set or see https://www.kaggle.com/docs/api"
        )
    return None


def init_command() -> str:
    kag_exe = shutil.which("kag")
    if not kag_exe:
        kag_exe = sys.executable + " -m kag.cli"

    return f'''kag() {{
    local kag_output
    kag_output=$({kag_exe} "$@" 2>/dev/null)
    local ret=$?
    if [ $ret -eq 0 ] && [ -n "$kag_output" ]; then
        cd "$kag_output"
    fi
    return $ret
}}'''


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        print(init_command())
        return

    error = check_kaggle_cli()
    if error:
        from rich.console import Console
        console = Console(stderr=True)
        console.print(f"[bold red]Error:[/bold red] {error}")
        sys.exit(1)

    from .tui import KagApp

    config = Config.load()
    app = KagApp(config=config)
    result = app.run()

    if result:
        print(result)