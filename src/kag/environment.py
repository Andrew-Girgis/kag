from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, EnvironmentConfig
from .context import content_hash, generated_hashes

PYPROJECT_NAME = "pyproject.toml"
VENV_NAME = ".venv"
LOG_PATH = Path(".kag") / "logs" / "environment.log"
DEFAULT_REQUIRES_PYTHON = ">=3.10"
POLL_SECONDS = 0.2
ISOLATED_ENV_VARS = ("UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV")


@dataclass
class EnvironmentResult:
    status: str
    packages: list[str] = field(default_factory=list)
    install_command: str = ""
    log: str | None = None
    message: str = ""

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {"status": self.status}
        if self.status != "disabled":
            payload["packages"] = self.packages
            payload["install_command"] = self.install_command
        if self.log:
            payload["log"] = self.log
        if self.message:
            payload["message"] = self.message
        return payload


def _should_run(config: Config, project_dir: Path) -> bool:
    if config.environment.command:
        return True
    return not (project_dir / VENV_NAME).exists() and owns_pyproject(project_dir)


def needs_prompt(config: Config, project_dir: Path) -> bool:
    return (
        config.auto_venv
        and config.environment.install == "ask"
        and _should_run(config, project_dir)
    )


def owns_pyproject(project_dir: Path) -> bool:
    path = project_dir / PYPROJECT_NAME
    if not path.exists():
        return True
    try:
        current = content_hash(path.read_text())
    except (OSError, UnicodeDecodeError):
        return False
    return generated_hashes(project_dir).get(PYPROJECT_NAME) == current


def planned_packages(project_dir: Path, config: Config) -> list[str]:
    path = project_dir / PYPROJECT_NAME
    if not path.exists():
        return list(config.environment.packages)
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return []
    project = data.get("project")
    dependencies = project.get("dependencies") if isinstance(project, dict) else None
    if not isinstance(dependencies, list):
        return []
    return [item for item in dependencies if isinstance(item, str)]


def wants_install(config: Config, install: bool | None) -> bool:
    if install is not None:
        return install
    return config.environment.install == "always"


def _project_name(slug: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-") or "kaggle-workspace"


def _requires_python(python: str) -> str:
    if re.fullmatch(r"3\.\d+", python):
        return f">={python}"
    return DEFAULT_REQUIRES_PYTHON


def render_pyproject(slug: str, environment: EnvironmentConfig) -> str:
    dependencies = "".join(f"    {json.dumps(package)},\n" for package in environment.packages)
    return (
        "[project]\n"
        f'name = "{_project_name(slug)}"\n'
        'version = "0.1.0"\n'
        f"description = {json.dumps(f'Kaggle workspace for {slug}, created by kag')}\n"
        f'requires-python = "{_requires_python(environment.python)}"\n'
        f"dependencies = [\n{dependencies}]\n"
        "\n"
        "[tool.uv]\n"
        "package = false\n"
        "\n"
        "[tool.uv.workspace]\n"
        "members = []\n"
    )


def write_pyproject(project_dir: Path, slug: str, config: Config) -> bool:
    if not config.auto_venv:
        return False
    path = project_dir / PYPROJECT_NAME
    if path.exists():
        return False
    path.write_text(render_pyproject(slug, config.environment))
    return True


def _fallback_python(python: str) -> str:
    if not python:
        return sys.executable
    return shutil.which(f"python{python}") or f"python{python}"


def install_commands(
    environment: EnvironmentConfig, packages: list[str] | None = None
) -> list[list[str]]:
    if environment.command:
        return [list(environment.command)]
    uv = shutil.which("uv")
    if uv:
        command = [uv, "sync"]
        if environment.python:
            command += ["--python", environment.python]
        return [command]
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    packages = environment.packages if packages is None else packages
    commands = [[_fallback_python(environment.python), "-m", "venv", VENV_NAME]]
    if packages:
        venv_python = str(Path(VENV_NAME) / bin_dir / "python")
        commands.append([venv_python, "-m", "pip", "install", *packages])
    return commands


def _display(command: list[str]) -> str:
    program = command[0]
    if program == sys.executable or Path(program).is_absolute():
        program = Path(program).name
    return shlex.join([program, *command[1:]])


def describe(commands: list[list[str]]) -> str:
    return " && ".join(_display(command) for command in commands)


def _child_env(custom: bool) -> dict[str, str] | None:
    if custom:
        return None
    return {key: value for key, value in os.environ.items() if key not in ISOLATED_ENV_VARS}


def _run(
    command: list[str],
    project_dir: Path,
    log_file,
    check_cancel: Callable[[], None],
    env: dict[str, str] | None = None,
) -> int:
    process = subprocess.Popen(
        command,
        cwd=str(project_dir),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    while True:
        try:
            return process.wait(timeout=POLL_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        try:
            check_cancel()
        except BaseException:
            _stop(process)
            raise


def _signal(process: subprocess.Popen, sig: int) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, sig)
            return
        except ProcessLookupError:
            return
        except OSError:
            pass
    if sig == signal.SIGTERM:
        process.terminate()
    else:
        process.kill()


def _stop(process: subprocess.Popen) -> None:
    _signal(process, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _signal(process, getattr(signal, "SIGKILL", signal.SIGTERM))
        process.wait()


def setup_environment(
    project_dir: Path,
    config: Config,
    install: bool,
    check_cancel: Callable[[], None],
    report: Callable[[str], None],
) -> EnvironmentResult:
    if not config.auto_venv:
        return EnvironmentResult(status="disabled")
    custom = bool(config.environment.command)
    if not custom and not (project_dir / VENV_NAME).exists() and not owns_pyproject(project_dir):
        return EnvironmentResult(
            status="user_managed",
            install_command="uv sync",
            message=f"the project has its own {PYPROJECT_NAME}, so kag doesn't install it",
        )
    packages = planned_packages(project_dir, config)
    commands = install_commands(config.environment, packages)
    base = {"packages": packages, "install_command": describe(commands)}
    if not _should_run(config, project_dir):
        return EnvironmentResult(status="exists", **base)
    if not install:
        return EnvironmentResult(status="not_installed", **base)
    venv_existed = (project_dir / VENV_NAME).exists()

    log_path = project_dir / LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = LOG_PATH.as_posix()
    env = _child_env(custom)
    with log_path.open("ab") as log_file:
        for command in commands:
            report(f"Setting up the Python environment: {_display(command)}")
            try:
                code = _run(command, project_dir, log_file, check_cancel, env)
            except OSError as exc:
                code = None
                message = f"couldn't run {_display(command)}: {exc}"
            else:
                message = f"{_display(command)} exited with code {code}"
            if code != 0:
                if not venv_existed:
                    shutil.rmtree(project_dir / VENV_NAME, ignore_errors=True)
                return EnvironmentResult(status="failed", log=log, message=message, **base)
    return EnvironmentResult(status="installed", log=log, **base)


def follow_up(result: EnvironmentResult, project_dir: Path) -> str | None:
    retry = f"cd {shlex.quote(str(project_dir))} && {result.install_command}"
    if result.status == "user_managed":
        return (
            f"This project has its own {PYPROJECT_NAME}, so kag didn't install anything. "
            f"Review it, then run: {retry}"
        )
    if result.status == "not_installed":
        return f"Python packages were not installed. To install them: {retry}"
    if result.status == "failed":
        return (
            f"Couldn't set up the Python environment ({result.message}). "
            f"See {project_dir / (result.log or LOG_PATH.as_posix())}. To retry: {retry}"
        )
    return None
