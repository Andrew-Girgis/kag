from __future__ import annotations

import json
import sys
import threading
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from kag import cli, config as config_module, environment, new_command, project
from kag.config import DEFAULT_PACKAGES, Config, EnvironmentConfig
from kag.environment import EnvironmentResult
from kag.kaggle_api import Competition
from kag.kaggle_sdk import CompetitionDetails
from kag.project import ProjectCreationCancelled


class FakeProcess:
    def __init__(self, returncode: int = 0, waits_before_exit: int = 0) -> None:
        self.returncode = returncode
        self.waits_before_exit = waits_before_exit
        self.terminated = False
        self.pid = 4242

    def wait(self, timeout: float | None = None) -> int:
        if self.terminated:
            return -15
        if self.waits_before_exit > 0:
            self.waits_before_exit -= 1
            raise environment.subprocess.TimeoutExpired("cmd", timeout or 0)
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.terminated = True


@pytest.fixture
def popen(monkeypatch: pytest.MonkeyPatch) -> dict:
    state: dict = {"calls": [], "processes": [], "returncode": 0, "waits": 0, "create": True}

    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        state["calls"].append({"cmd": list(cmd), **kwargs})
        if state["create"]:
            (Path(str(kwargs["cwd"])) / ".venv").mkdir(exist_ok=True)
        process = FakeProcess(state["returncode"], state["waits"])
        state["processes"].append(process)
        return process

    monkeypatch.setattr(environment.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(environment.shutil, "which", lambda cmd: f"/usr/local/bin/{cmd}")
    return state


def _write_config(home: Path, text: str) -> None:
    (home / ".kag_config.toml").write_text(text)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(config_module.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("KAG_PATH", raising=False)
    return tmp_path


def test_environment_defaults_ask_before_installing(home: Path) -> None:
    config = Config.load()

    assert config.auto_venv is True
    assert config.environment == EnvironmentConfig()
    assert config.environment.install == "ask"
    assert config.environment.packages == list(DEFAULT_PACKAGES)


def test_environment_section_is_fully_configurable(home: Path) -> None:
    _write_config(
        home,
        "[environment]\n"
        "create = true\n"
        'install = "always"\n'
        'python = "3.12"\n'
        'packages = ["polars", "lightgbm"]\n'
        'command = ["pixi", "install"]\n',
    )

    config = Config.load()

    assert config.environment == EnvironmentConfig(
        install="always",
        python="3.12",
        packages=["polars", "lightgbm"],
        command=["pixi", "install"],
    )


def test_environment_create_false_and_legacy_auto_venv_disable_it(home: Path) -> None:
    _write_config(home, "[environment]\ncreate = false\n")
    assert Config.load().auto_venv is False

    _write_config(home, "auto_venv = false\n")
    assert Config.load().auto_venv is False


def test_invalid_environment_values_fall_back_to_safe_defaults(home: Path) -> None:
    _write_config(
        home,
        "[environment]\n"
        'install = "sometimes"\n'
        "python = 3\n"
        'packages = "pandas"\n'
        'command = ["", "x"]\n',
    )

    assert Config.load().environment == EnvironmentConfig()


def test_render_pyproject_lists_exactly_the_configured_packages() -> None:
    text = environment.render_pyproject(
        "Some_Comp.2026", EnvironmentConfig(python="3.12", packages=["pandas", "scikit-learn>=1.5"])
    )

    data = tomllib.loads(text)
    assert data["project"]["name"] == "some-comp-2026"
    assert data["project"]["requires-python"] == ">=3.12"
    assert data["project"]["dependencies"] == ["pandas", "scikit-learn>=1.5"]
    assert data["tool"]["uv"]["package"] is False


def test_render_pyproject_with_no_packages_is_valid() -> None:
    data = tomllib.loads(environment.render_pyproject("titanic", EnvironmentConfig(packages=[])))

    assert data["project"]["dependencies"] == []
    assert data["project"]["requires-python"] == environment.DEFAULT_REQUIRES_PYTHON


def test_install_commands_prefer_custom_command_then_uv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(environment.shutil, "which", lambda cmd: "/opt/bin/uv")

    assert environment.install_commands(EnvironmentConfig(command=["pixi", "install"])) == [
        ["pixi", "install"]
    ]
    commands = environment.install_commands(EnvironmentConfig(python="3.12"))
    assert commands == [["/opt/bin/uv", "sync", "--python", "3.12"]]
    assert environment.describe(commands) == "uv sync --python 3.12"


def test_install_commands_fall_back_to_venv_and_pip_without_uv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(environment.shutil, "which", lambda cmd: None)

    commands = environment.install_commands(EnvironmentConfig(packages=["pandas"]))

    assert commands[0] == [sys.executable, "-m", "venv", ".venv"]
    assert commands[1][-4:] == ["-m", "pip", "install", "pandas"]


def _setup(project_dir: Path, config: Config, install: bool, **kwargs: object) -> EnvironmentResult:
    project_dir.mkdir(exist_ok=True)
    return environment.setup_environment(
        project_dir, config, install, kwargs.get("check_cancel", lambda: None), lambda _: None
    )


def test_setup_environment_does_nothing_unless_install_is_chosen(
    tmp_path: Path, popen: dict
) -> None:
    result = _setup(tmp_path / "p", Config(kag_path=tmp_path), install=False)

    assert result.status == "not_installed"
    assert result.install_command == "uv sync"
    assert result.packages == list(DEFAULT_PACKAGES)
    assert popen["calls"] == []
    assert not (tmp_path / "p" / ".venv").exists()


def test_setup_environment_installs_and_logs(tmp_path: Path, popen: dict) -> None:
    project_dir = tmp_path / "p"

    result = _setup(project_dir, Config(kag_path=tmp_path), install=True)

    assert result.status == "installed"
    call = popen["calls"][0]
    assert call["cmd"] == ["/usr/local/bin/uv", "sync"]
    assert call["cwd"] == str(project_dir)
    assert call["stdin"] is environment.subprocess.DEVNULL
    assert (project_dir / environment.LOG_PATH).exists()


def test_setup_environment_reports_failure_and_removes_partial_venv(
    tmp_path: Path, popen: dict
) -> None:
    popen["returncode"] = 2
    project_dir = tmp_path / "p"

    result = _setup(project_dir, Config(kag_path=tmp_path), install=True)

    assert result.status == "failed"
    assert "exited with code 2" in result.message
    assert result.log == environment.LOG_PATH.as_posix()
    assert not (project_dir / ".venv").exists()
    follow_up = environment.follow_up(result, project_dir)
    assert follow_up is not None and "uv sync" in follow_up


def test_setup_environment_reports_missing_custom_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(cmd: list[str], **kwargs: object) -> None:
        raise FileNotFoundError(2, "No such file", cmd[0])

    monkeypatch.setattr(environment.subprocess, "Popen", missing)
    config = Config(kag_path=tmp_path, environment=EnvironmentConfig(command=["pixi", "install"]))

    result = _setup(tmp_path / "p", config, install=True)

    assert result.status == "failed"
    assert "couldn't run pixi install" in result.message


def test_setup_environment_skips_existing_venv_and_disabled_config(
    tmp_path: Path, popen: dict
) -> None:
    (tmp_path / "p" / ".venv").mkdir(parents=True)

    assert _setup(tmp_path / "p", Config(kag_path=tmp_path), install=True).status == "exists"
    disabled = _setup(tmp_path / "q", Config(kag_path=tmp_path, auto_venv=False), install=True)
    assert disabled.status == "disabled"
    assert disabled.to_json() == {"status": "disabled"}
    assert popen["calls"] == []


def test_setup_environment_stops_the_install_when_cancelled(
    tmp_path: Path, popen: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    popen["waits"] = 100
    cancel = threading.Event()
    checks = {"count": 0}

    def check_cancel() -> None:
        checks["count"] += 1
        if checks["count"] >= 2:
            cancel.set()
            raise ProjectCreationCancelled("Project setup cancelled")

    signals: list[tuple[int, int]] = []

    def killpg(pid: int, sig: int) -> None:
        signals.append((pid, sig))
        popen["processes"][0].terminated = True

    monkeypatch.setattr(environment.os, "killpg", killpg)

    with pytest.raises(ProjectCreationCancelled):
        _setup(tmp_path / "p", Config(kag_path=tmp_path), install=True, check_cancel=check_cancel)

    assert signals == [(4242, environment.signal.SIGTERM)]
    assert popen["calls"][0]["start_new_session"] is True


def test_missing_requested_python_is_not_silently_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(environment.shutil, "which", lambda cmd: None)

    commands = environment.install_commands(EnvironmentConfig(python="3.99"))

    assert commands[0][0] == "python3.99"


def test_custom_command_runs_even_with_an_existing_venv(tmp_path: Path, popen: dict) -> None:
    popen["create"] = False
    popen["returncode"] = 1
    project_dir = tmp_path / "p"
    (project_dir / ".venv").mkdir(parents=True)
    (project_dir / ".venv" / "keep").write_text("mine")
    config = Config(kag_path=tmp_path, environment=EnvironmentConfig(command=["pixi", "install"]))

    assert environment.needs_prompt(config, project_dir) is True
    result = _setup(project_dir, config, install=True)

    assert popen["calls"][0]["cmd"] == ["pixi", "install"]
    assert result.status == "failed"
    assert (project_dir / ".venv" / "keep").read_text() == "mine"


def _stub_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(project, "get_competition_files", lambda slug: ["train.csv"])
    monkeypatch.setattr(
        project, "fetch_competition_markdown_sections", lambda slug, **kwargs: ({}, [])
    )
    monkeypatch.setattr(
        project.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="")
    )


def _create(tmp_path: Path, config: Config, **kwargs: object) -> list[EnvironmentResult]:
    results: list[EnvironmentResult] = []
    project.create_project(
        Competition(slug="titanic", title="Titanic", deadline="", reward="", team_count="0"),
        config,
        download_files=False,
        on_environment=results.append,
        **kwargs,
    )
    return results


def test_create_project_writes_pyproject_but_asks_before_installing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, popen: dict
) -> None:
    _stub_sources(monkeypatch)

    results = _create(tmp_path, Config(kag_path=tmp_path, auto_git=False))

    project_dir = tmp_path / "titanic"
    pyproject = tomllib.loads((project_dir / "pyproject.toml").read_text())
    assert pyproject["project"]["dependencies"] == list(DEFAULT_PACKAGES)
    assert [result.status for result in results] == ["not_installed"]
    assert popen["calls"] == []
    agents = (project_dir / "AGENTS.md").read_text()
    assert "`pyproject.toml`" in agents
    assert "Ask the user before installing packages" in agents


@pytest.mark.parametrize(
    ("install_mode", "install_environment", "expected"),
    [
        ("always", None, "installed"),
        ("never", None, "not_installed"),
        ("ask", True, "installed"),
        ("always", False, "not_installed"),
    ],
)
def test_create_project_install_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    popen: dict,
    install_mode: str,
    install_environment: bool | None,
    expected: str,
) -> None:
    _stub_sources(monkeypatch)
    config = Config(
        kag_path=tmp_path, auto_git=False, environment=EnvironmentConfig(install=install_mode)
    )

    results = _create(tmp_path, config, install_environment=install_environment)

    assert results[0].status == expected


def test_create_project_keeps_users_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, popen: dict
) -> None:
    _stub_sources(monkeypatch)
    (tmp_path / "titanic").mkdir()
    (tmp_path / "titanic" / "pyproject.toml").write_text("# mine\n")

    _create(tmp_path, Config(kag_path=tmp_path, auto_git=False))

    assert (tmp_path / "titanic" / "pyproject.toml").read_text() == "# mine\n"


def test_create_project_without_environment_writes_no_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, popen: dict
) -> None:
    _stub_sources(monkeypatch)

    results = _create(tmp_path, Config(kag_path=tmp_path, auto_git=False, auto_venv=False))

    assert not (tmp_path / "titanic" / "pyproject.toml").exists()
    assert "pyproject.toml" not in (tmp_path / "titanic" / "AGENTS.md").read_text()
    assert results[0].status == "disabled"


def test_create_project_commits_pyproject_with_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, popen: dict
) -> None:
    _stub_sources(monkeypatch)
    seen: list[bool] = []

    def record(cmd: list[str], *args: object, **kwargs: object) -> SimpleNamespace:
        if cmd[:2] == ["git", "add"]:
            seen.append((tmp_path / "titanic" / "pyproject.toml").exists())
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(project.subprocess, "run", record)

    _create(tmp_path, Config(kag_path=tmp_path, auto_git=True))

    assert seen == [True]


@pytest.fixture
def new_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    state: dict = {"calls": [], "result": EnvironmentResult("not_installed", ["pandas"], "uv sync")}
    config = Config(kag_path=tmp_path)
    monkeypatch.setattr(new_command.Config, "load", classmethod(lambda cls: config))
    monkeypatch.setattr(
        new_command,
        "fetch_competition_details",
        lambda slug: CompetitionDetails(slug=slug, title="Titanic"),
    )
    monkeypatch.setattr(new_command, "check_competition_access", lambda slug: (True, "ok"))
    monkeypatch.setattr(cli, "check_kaggle_cli", lambda: None)

    def fake_create_project(**kwargs: object) -> str:
        state["calls"].append(kwargs)
        (tmp_path / "titanic").mkdir(exist_ok=True)
        kwargs["on_environment"](state["result"])  # type: ignore[operator]
        return str(tmp_path / "titanic")

    monkeypatch.setattr(new_command, "create_project", fake_create_project)
    state["root"] = tmp_path
    return state


def _run_new(capsys: pytest.CaptureFixture[str], *argv: str) -> dict:
    assert new_command.run_new(["titanic", *argv, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_kag_new_reports_packages_it_did_not_install(
    new_env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _run_new(capsys)

    assert new_env["calls"][0]["install_environment"] is None
    assert result["environment"] == {
        "status": "not_installed",
        "packages": ["pandas"],
        "install_command": "uv sync",
    }
    assert result["next_steps"][-1] == ("Ask the user before installing Python packages: uv sync")


def test_kag_new_install_flag_opts_in(new_env: dict, capsys: pytest.CaptureFixture[str]) -> None:
    new_env["result"] = EnvironmentResult(
        "installed", ["pandas"], "uv sync", log=".kag/logs/environment.log"
    )

    result = _run_new(capsys, "--install")

    assert new_env["calls"][0]["install_environment"] is True
    assert result["environment"]["status"] == "installed"
    assert len(result["next_steps"]) == 2


def test_kag_new_warns_when_install_fails(
    new_env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    new_env["result"] = EnvironmentResult(
        "failed", ["pandas"], "uv sync", log=".kag/logs/environment.log", message="uv sync exited"
    )

    result = _run_new(capsys, "--install")

    assert result["environment"]["status"] == "failed"
    assert any("Couldn't set up the Python environment" in w for w in result["warnings"])


def test_generated_pyproject_is_its_own_uv_workspace() -> None:
    data = tomllib.loads(environment.render_pyproject("titanic", EnvironmentConfig()))

    assert data["tool"]["uv"]["workspace"] == {"members": []}


def test_create_project_installs_before_the_initial_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, popen: dict
) -> None:
    _stub_sources(monkeypatch)
    order: list[str] = []

    def record(cmd: list[str], *args: object, **kwargs: object) -> SimpleNamespace:
        if cmd[:2] == ["git", "add"]:
            order.append("git add")
        return SimpleNamespace(returncode=0, stdout="")

    original = environment.subprocess.Popen

    def recording_popen(cmd: list[str], **kwargs: object) -> object:
        order.append("install")
        return original(cmd, **kwargs)

    monkeypatch.setattr(project.subprocess, "run", record)
    monkeypatch.setattr(environment.subprocess, "Popen", recording_popen)

    _create(tmp_path, Config(kag_path=tmp_path, auto_git=True), install_environment=True)

    assert order == ["install", "git add"]


def test_users_own_pyproject_is_never_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, popen: dict
) -> None:
    _stub_sources(monkeypatch)
    (tmp_path / "titanic").mkdir()
    (tmp_path / "titanic" / "pyproject.toml").write_text(
        '[project]\nname = "t"\ndependencies = ["torch"]\n[tool.uv.sources]\n'
        'torch = { git = "https://example.com/torch" }\n'
    )
    config = Config(kag_path=tmp_path, auto_git=False)

    assert environment.needs_prompt(config, tmp_path / "titanic") is False
    results = _create(tmp_path, config, install_environment=True)

    assert results[0].status == "user_managed"
    assert results[0].packages == []
    assert popen["calls"] == []
    message = environment.follow_up(results[0], tmp_path / "titanic")
    assert message is not None and "its own pyproject.toml" in message


def test_kag_pyproject_stays_installable_until_edited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, popen: dict
) -> None:
    _stub_sources(monkeypatch)
    project_dir = tmp_path / "titanic"
    config = Config(kag_path=tmp_path, auto_git=False)

    _create(tmp_path, config)
    assert environment.owns_pyproject(project_dir) is True
    assert environment.needs_prompt(config, project_dir) is True

    results = _create(tmp_path, config, install_environment=True)
    assert results[0].status == "installed"
    assert results[0].packages == list(DEFAULT_PACKAGES)

    (project_dir / "pyproject.toml").write_text(
        (project_dir / "pyproject.toml").read_text().replace('"pandas"', '"pandas", "torch"')
    )
    assert environment.owns_pyproject(project_dir) is False


def test_custom_command_still_runs_for_a_users_pyproject(tmp_path: Path, popen: dict) -> None:
    project_dir = tmp_path / "p"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text('[project]\nname = "p"\n')
    config = Config(kag_path=tmp_path, environment=EnvironmentConfig(command=["pixi", "install"]))

    result = _setup(project_dir, config, install=True)

    assert result.status == "installed"
    assert popen["calls"][0]["cmd"] == ["pixi", "install"]


def test_pip_fallback_installs_exactly_the_listed_packages(
    tmp_path: Path, popen: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(environment.shutil, "which", lambda cmd: None)
    config = Config(kag_path=tmp_path, environment=EnvironmentConfig(packages=["polars"]))

    result = _setup(tmp_path / "p", config, install=True)

    assert result.packages == ["polars"]
    assert popen["calls"][1]["cmd"][-4:] == ["-m", "pip", "install", "polars"]


def test_kag_new_tells_agents_about_a_users_pyproject(
    new_env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    new_env["result"] = EnvironmentResult(
        "user_managed", install_command="uv sync", message="own pyproject"
    )

    result = _run_new(capsys, "--install")

    assert result["environment"]["status"] == "user_managed"
    assert "its own pyproject.toml" in result["next_steps"][-1]
