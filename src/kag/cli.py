import json
import os
import sys
import shutil
import subprocess
from pathlib import Path

from . import __version__, kaggle_sdk
from .kaggle_api import KAGGLE_CLI_MISSING, bundled_kaggle_available, kaggle_command
from .config import Config


RESULT_FILE = Path.home() / ".kag_result"

HELP_TEXT = """Usage:
  kag [query]              Open the competition picker, optionally searching
  kag search <query>       Open the picker with a search query
  kag new <competition>    Create a workspace without the TUI (scripts and agents)
  kag login                Sign in to Kaggle in your browser
  kag doctor [--json]      Check your environment
  kag init                 Print shell integration that cds into new projects
  kag kaggle <args>        Run the Kaggle CLI bundled with kag

Options:
  -h, --help               Show this help (or `kag <command> --help`)
  --version                Show the installed version

A bare query searches unless it is a command name; use `kag search <query>` to
search for words like "new" or "login"."""

SEARCH_HELP_TEXT = """Usage:
  kag search <query>

Open the competition picker with <query> typed into the search box.
`kag <query>` does the same unless the first word is a command name.
Use `kag search -- <query>` to search for text that starts with "-"."""

DOCTOR_HELP_TEXT = """Usage:
  kag doctor [--json]

Check the bundled Kaggle CLI and library, Kaggle credentials and access,
KAG_PATH, the shell hook, and detected editors. Exits 1 only when a required
check fails; the shell hook, editors, and kag on PATH are optional (WARN).

Options:
  --json    Print machine-readable results."""

INIT_HELP_TEXT = '''Usage:
  kag init

Print a shell function that makes kag cd into the project you open. Add this to
~/.zshrc or ~/.bashrc:

  eval "$(kag init)"'''

COMMANDS = ("search", "new", "login", "doctor", "init", "kaggle")
HELP_FLAGS = ("-h", "--help")


KAGGLE_LOGIN_HINT = "run `kag login` or set KAGGLE_API_TOKEN"


LOGIN_HELP_TEXT = """Usage:
  kag login

Sign in to Kaggle in your browser using the Kaggle CLI bundled with kag
(`kaggle auth login`). Credentials are cached in ~/.kaggle/ and shared with the
kaggle command. If you are already logged in this does nothing; pass --force to
sign in again. Alternatively set KAGGLE_API_TOKEN."""


def _kaggle_config_dir() -> Path:
    config_dir = os.environ.get("KAGGLE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir).expanduser()
    default_dir = Path.home() / ".kaggle"
    if sys.platform.startswith("linux") and not default_dir.exists():
        xdg_config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        return Path(xdg_config) / "kaggle"
    return default_dir


def _has_text(path: Path) -> bool:
    try:
        return bool(path.read_text().strip())
    except OSError:
        return False


def _read_kaggle_json(path: Path) -> tuple[dict[str, object], str | None]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}, f"{path} is empty or not valid JSON"
    if not isinstance(data, dict):
        return {}, f"{path} is not a JSON object"
    return data, None


def _kaggle_auth_status() -> tuple[bool, str]:
    kaggle_home = Path.home() / ".kaggle"

    if os.environ.get("KAGGLE_API_TOKEN"):
        return True, "KAGGLE_API_TOKEN"
    for token_name in ("access_token", "access_token.txt"):
        token_path = kaggle_home / token_name
        if _has_text(token_path):
            return True, str(token_path)

    problems: list[str] = []
    file_values: dict[str, object] = {}
    kaggle_json = _kaggle_config_dir() / "kaggle.json"
    if kaggle_json.exists():
        file_values, problem = _read_kaggle_json(kaggle_json)
        if problem:
            problems.append(problem)

    env_username = os.environ.get("KAGGLE_USERNAME")
    env_key = os.environ.get("KAGGLE_KEY")
    if (env_username or file_values.get("username")) and (env_key or file_values.get("key")):
        if env_username and env_key:
            return True, "KAGGLE_USERNAME + KAGGLE_KEY"
        if not env_username and not env_key:
            return True, f"{kaggle_json} (legacy)"
        env_name = "KAGGLE_USERNAME" if env_username else "KAGGLE_KEY"
        return True, f"{kaggle_json} + {env_name} (legacy)"
    if kaggle_json.exists() and not problems:
        problems.append(f"{kaggle_json} is missing username or key")

    oauth_credentials = kaggle_home / "credentials.json"
    if _has_text(oauth_credentials):
        return True, f"{oauth_credentials} (kaggle auth login)"

    problems.append(f"no credentials found; {KAGGLE_LOGIN_HINT}")
    return False, "; ".join(problems)


def _first_output_line(*outputs: str | None) -> str:
    for output in outputs:
        text = (output or "").strip()
        if text:
            return text.splitlines()[0]
    return ""


def check_kaggle_cli() -> str | None:
    if not bundled_kaggle_available():
        return f"{KAGGLE_CLI_MISSING}: uv tool install --force kag"
    return None


def _auth_probe() -> tuple[bool, str]:
    try:
        probe = subprocess.run(
            kaggle_command("competitions", "list", "--csv", "--page-size", "1"),
            capture_output=True,
            text=True,
            timeout=12,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout running auth probe"
    except Exception as exc:
        return False, f"probe error: {exc}"
    if probe.returncode == 0:
        return True, "validated via `kaggle competitions list --page-size 1`"
    details = _first_output_line(probe.stderr, probe.stdout) or "command failed"
    if any(marker in details.lower() for marker in ("authenticat", "unauthorized", "401")):
        details += f" ({KAGGLE_LOGIN_HINT})"
    return False, details


def kaggle_passthrough(args: list[str]) -> int:
    cli_error = check_kaggle_cli()
    if cli_error:
        print(cli_error, file=sys.stderr)
        return 1
    return subprocess.run(kaggle_command(*args)).returncode


def login_command(args: list[str]) -> int:
    if "-h" in args or "--help" in args:
        print(LOGIN_HELP_TEXT)
        return 0
    cli_error = check_kaggle_cli()
    if cli_error:
        print(cli_error, file=sys.stderr)
        return 1
    if "--force" not in args and _auth_probe()[0]:
        print("Already logged in to Kaggle. Use `kag login --force` to sign in again.")
        return 0
    result = subprocess.run(kaggle_command("auth", "login", *args))
    ok, details = _auth_probe()
    if result.returncode != 0 and not ok:
        print("Kaggle login did not complete.", file=sys.stderr)
        return result.returncode
    if ok:
        print("Logged in. kag can reach Kaggle.")
        return 0
    print(f"Login finished but Kaggle still rejected the request: {details}", file=sys.stderr)
    return 1


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


def _shell_rc_files(shell: str) -> list[Path]:
    home = Path.home()
    zdotdir = Path(os.environ.get("ZDOTDIR") or home)
    zsh = [zdotdir / ".zshrc"]
    bash = [home / ".bashrc", home / ".bash_profile", home / ".profile"]
    if shell == "zsh":
        return zsh
    if shell == "bash":
        return bash
    return zsh + bash


def _shell_hook_status() -> tuple[bool, str]:
    shell = Path(os.environ.get("SHELL", "")).name
    if shell == "fish":
        return False, "fish isn't supported yet; kag still works, but won't cd into the project"
    rc_files = _shell_rc_files(shell)
    for rc_file in rc_files:
        try:
            text = rc_file.read_text(errors="ignore")
        except OSError:
            continue
        if "kag init" in text or "kag --init" in text:
            return True, str(rc_file)
    checked = ", ".join(str(rc_file) for rc_file in rc_files)
    return False, f'not found in {checked}; add eval "$(kag init)" to cd into new projects'


def doctor_command(json_output: bool = False) -> int:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    config = Config.load()

    checks: list[dict[str, str | bool]] = []

    def add_check(name: str, ok: bool, details: str, required: bool = True) -> None:
        status = "ok" if ok else "fail" if required else "warn"
        checks.append(
            {
                "name": name,
                "ok": ok,
                "required": required,
                "status": status,
                "details": details,
            }
        )

    kag_bin = shutil.which("kag")
    add_check(
        "kag on PATH",
        kag_bin is not None,
        kag_bin or "not found (fine when running from a checkout with `uv run kag`)",
        required=False,
    )

    cli_available = bundled_kaggle_available()
    if cli_available:
        version = "unknown"
        try:
            proc = subprocess.run(
                kaggle_command("--version"),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0:
                version = proc.stdout.strip() or "unknown"
        except Exception:
            pass
        add_check("kaggle CLI", True, f"bundled with kag ({version})")
    else:
        add_check("kaggle CLI", False, f"{KAGGLE_CLI_MISSING}: uv tool install --force kag")

    library_version = kaggle_sdk.sdk_version()
    add_check(
        "kaggle python library",
        library_version is not None,
        f"kaggle {library_version}" if library_version else "not installed (reinstall kag)",
    )

    auth_ok, auth_details = _kaggle_auth_status()
    add_check("kaggle credentials", auth_ok, auth_details)

    auth_runtime_ok, auth_runtime_details = (
        _auth_probe() if cli_available else (False, "skipped (bundled Kaggle CLI unavailable)")
    )
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
    add_check("result file writable", result_writable, str(RESULT_FILE), required=False)

    shell_hook_ok, shell_hook_details = _shell_hook_status()
    add_check("shell hook", shell_hook_ok, shell_hook_details, required=False)

    editors = config.available_editors()
    add_check(
        "detected editors",
        len(editors) > 0,
        ", ".join(editor["cmd"] for editor in editors)
        if editors
        else "none (projects are created without opening an editor)",
        required=False,
    )

    has_failure = any(check["status"] == "fail" for check in checks)
    has_warning = any(check["status"] == "warn" for check in checks)

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

    labels = {"ok": "[green]OK[/green]", "warn": "[yellow]WARN[/yellow]", "fail": "[red]FAIL[/red]"}
    for check in checks:
        table.add_row(str(check["name"]), labels[str(check["status"])], str(check["details"]))

    console.print(table)
    if has_failure:
        console.print(
            "\n[bold red]Doctor found issues.[/bold red] Fix FAIL rows and re-run `kag doctor`."
        )
        return 1
    if has_warning:
        console.print("\n[bold green]Required checks passed.[/bold green] WARN rows are optional.")
        return 0
    console.print("\n[bold green]All checks passed.[/bold green]")
    return 0


def _usage_error(message: str) -> int:
    print(f"kag: {message}", file=sys.stderr)
    print("Run `kag --help` for usage.", file=sys.stderr)
    return 2


def _command_help(args: list[str], text: str) -> bool:
    if any(arg in HELP_FLAGS for arg in args):
        print(text)
        return True
    return False


def run_tui(initial_query: str) -> int:
    error = check_kaggle_cli()
    if error:
        from rich.console import Console

        Console(stderr=True).print(f"[bold red]Error:[/bold red] {error}")
        return 1

    from .tui import KagApp

    app = KagApp(config=Config.load(), initial_query=initial_query)
    app.run()
    if app.result:
        RESULT_FILE.write_text(app.result)
    return 0


def run_command(args: list[str]) -> int:
    if not args:
        return run_tui("")

    command, rest = args[0], args[1:]
    if command == "--init":
        command = "init"
    elif command == "--doctor":
        command = "doctor"

    if command == "new":
        from .new_command import run_new

        return run_new(rest)
    if command == "login":
        return login_command(rest)
    if command == "kaggle":
        return kaggle_passthrough(rest)
    if command == "init":
        if _command_help(rest, INIT_HELP_TEXT):
            return 0
        if rest:
            return _usage_error(f"init takes no arguments: {' '.join(rest)}")
        print(init_command())
        return 0
    if command == "doctor":
        if _command_help(rest, DOCTOR_HELP_TEXT):
            return 0
        unknown = [arg for arg in rest if arg != "--json"]
        if unknown:
            return _usage_error(f"unknown doctor option: {unknown[0]}")
        return doctor_command(json_output="--json" in rest)
    if command == "search":
        words = rest
        if "--" in rest:
            separator = rest.index("--")
            words, literal = rest[:separator], rest[separator + 1 :]
        else:
            literal = []
        if _command_help(words, SEARCH_HELP_TEXT):
            return 0
        option = next((arg for arg in words if arg.startswith("-")), None)
        if option is not None:
            return _usage_error(f"unknown search option: {option}")
        return run_tui(" ".join([*words, *literal]).strip())

    if any(arg in HELP_FLAGS for arg in args):
        print(HELP_TEXT)
        return 0
    if command == "--version":
        print(f"kag {__version__}")
        return 0
    option = next((arg for arg in args if arg.startswith("-")), None)
    if option is not None:
        return _usage_error(f"unknown option: {option}")
    return run_tui(" ".join(args).strip())


def main() -> None:
    code = run_command(sys.argv[1:])
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
