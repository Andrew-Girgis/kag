import json
import os
import sys
import shutil
import subprocess
from pathlib import Path

from .config import Config


RESULT_FILE = Path.home() / ".kag_result"


def _kaggle_auth_status() -> tuple[bool, str]:
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    api_token = os.environ.get("KAGGLE_API_TOKEN")
    username = os.environ.get("KAGGLE_USERNAME")
    key = os.environ.get("KAGGLE_KEY")

    if api_token:
        return True, "KAGGLE_API_TOKEN"
    if username and key:
        return True, "KAGGLE_USERNAME + KAGGLE_KEY"
    if kaggle_json.exists():
        return True, f"{kaggle_json} (legacy)"
    return False, "missing (set KAGGLE_API_TOKEN or KAGGLE_USERNAME/KAGGLE_KEY)"


def check_kaggle_cli() -> str | None:
    kaggle_path = shutil.which("kaggle")
    if not kaggle_path:
        return "kaggle CLI not found. Install with: pip install kaggle"
    auth_ok, auth_details = _kaggle_auth_status()
    if not auth_ok:
        return (
            "kaggle credentials not found.\n"
            "Set KAGGLE_API_TOKEN (preferred) or KAGGLE_USERNAME/KAGGLE_KEY, "
            "or use legacy ~/.kaggle/kaggle.json."
        )
    return None


def _find_kag_exe() -> str:
    kag_exe = shutil.which("kag")
    if kag_exe:
        return kag_exe
    project_dir = Path(__file__).resolve().parent.parent
    venv_python = project_dir / ".venv" / "bin" / "python"
    if venv_python.exists():
        return f"{venv_python} -m kag.cli"
    return sys.executable + " -m kag.cli"


def init_command() -> str:
    kag_exe = _find_kag_exe()

    return f'''kag() {{
    rm -f "{RESULT_FILE}"
    {kag_exe} "$@"
    local ret=$?
    if [ $ret -eq 0 ] && [ -f "{RESULT_FILE}" ]; then
        local kag_output
        kag_output=$(cat "{RESULT_FILE}")
        rm -f "{RESULT_FILE}"
        if [ -n "$kag_output" ]; then
            cd "$kag_output"
        fi
    fi
    return $ret
}}'''


def _check_writable(path: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        probe = path.parent / ".kag_write_probe"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def doctor_command(json_output: bool = False) -> int:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    config = Config.load()

    checks: list[dict[str, str | bool]] = []

    def add_check(name: str, ok: bool, details: str) -> None:
        checks.append({"name": name, "ok": ok, "details": details})

    kag_bin = shutil.which("kag")
    add_check("kag on PATH", kag_bin is not None, kag_bin or "not found")

    kaggle_bin = shutil.which("kaggle")
    if kaggle_bin:
        version = "unknown"
        try:
            proc = subprocess.run(
                ["kaggle", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0:
                version = proc.stdout.strip() or "unknown"
        except Exception:
            pass
        add_check("kaggle CLI", True, f"{kaggle_bin} ({version})")
    else:
        add_check("kaggle CLI", False, "not found")

    auth_ok, auth_details = _kaggle_auth_status()
    add_check("kaggle credentials", auth_ok, auth_details)

    auth_runtime_ok = False
    auth_runtime_details = "skipped (kaggle CLI unavailable)"
    if kaggle_bin:
        try:
            auth_probe = subprocess.run(
                ["kaggle", "competitions", "list", "--csv", "--page-size", "1"],
                capture_output=True,
                text=True,
                timeout=12,
            )
            if auth_probe.returncode == 0:
                auth_runtime_ok = True
                auth_runtime_details = "validated via `kaggle competitions list --page-size 1`"
            else:
                stderr = (auth_probe.stderr or "").strip()
                auth_runtime_details = stderr.splitlines()[0] if stderr else "command failed"
        except subprocess.TimeoutExpired:
            auth_runtime_details = "timeout running auth probe"
        except Exception as exc:
            auth_runtime_details = f"probe error: {exc}"
    add_check("kaggle auth probe", auth_runtime_ok, auth_runtime_details)

    kag_path_exists = config.kag_path.exists()
    kag_path_writable = _check_writable(config.kag_path / ".probe")
    kag_path_ok = kag_path_writable
    kag_path_note = "exists" if kag_path_exists else "will be created"
    add_check(
        "KAG_PATH",
        kag_path_ok,
        f"{config.kag_path} ({kag_path_note}, writable={kag_path_writable})",
    )

    result_writable = _check_writable(RESULT_FILE)
    add_check("result file writable", result_writable, str(RESULT_FILE))

    zshrc = Path.home() / ".zshrc"
    shell_hook_ok = False
    if zshrc.exists():
        text = zshrc.read_text(errors="ignore")
        shell_hook_ok = "kag --init" in text or "kag init" in text
    add_check("shell hook in .zshrc", shell_hook_ok, str(zshrc))

    editors = config.available_editors()
    add_check(
        "detected editors",
        len(editors) > 0,
        ", ".join(editor["cmd"] for editor in editors) if editors else "none",
    )

    has_failure = any(not bool(check["ok"]) for check in checks)

    if json_output:
        payload = {
            "ok": not has_failure,
            "checks": checks,
        }
        print(json.dumps(payload, indent=2))
        return 1 if has_failure else 0

    table = Table(title="kag doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Details")

    for check in checks:
        name = str(check["name"])
        ok = bool(check["ok"])
        details = str(check["details"])
        status = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
        table.add_row(name, status, details)

    console.print(table)
    if has_failure:
        console.print("\n[bold red]Doctor found issues.[/bold red] Fix FAIL rows and re-run `kag doctor`.")
        return 1
    console.print("\n[bold green]All checks passed.[/bold green]")
    return 0


def main() -> None:
    args = sys.argv[1:]

    if "--init" in args:
        print(init_command())
        return
    if "--doctor" in args:
        json_output = "--json" in args
        raise SystemExit(doctor_command(json_output=json_output))

    error = check_kaggle_cli()
    if error:
        from rich.console import Console
        console = Console(stderr=True)
        console.print(f"[bold red]Error:[/bold red] {error}")
        sys.exit(1)

    from .tui import KagApp

    initial_query = " ".join(args).strip() if args else ""
    config = Config.load()
    app = KagApp(config=config, initial_query=initial_query)
    app.run()
    result = app.result

    if result:
        RESULT_FILE.write_text(result)
