from __future__ import annotations

import _thread
import json
import threading
from pathlib import Path

import pytest

from kag import cli, new_command
from kag.config import Config
from kag.kaggle_sdk import CompetitionDetails
from kag.project import ProjectCreationCancelled, ProjectCreationError


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    state: dict = {"calls": [], "access": (True, "Access confirmed"), "access_calls": 0}
    config = Config(kag_path=tmp_path)
    monkeypatch.setattr(new_command.Config, "load", classmethod(lambda cls: config))
    monkeypatch.setattr(
        new_command,
        "fetch_competition_details",
        lambda slug: CompetitionDetails(slug=slug, title="Titanic - ML from Disaster"),
    )

    def access(slug: str) -> tuple[bool, str]:
        state["access_calls"] += 1
        return state["access"]

    def fake_create_project(**kwargs: object) -> str:
        state["calls"].append(kwargs)
        project_dir = tmp_path / kwargs["competition"].slug  # type: ignore[attr-defined]
        project_dir.mkdir(exist_ok=True)
        for name in ("AGENTS.md", "notes.md", "CLAUDE.md"):
            if not (project_dir / name).exists():
                (project_dir / name).write_text(name)
        if kwargs["download_files"]:
            (project_dir / "data").mkdir(exist_ok=True)
            (project_dir / "data" / "train.csv").write_text("a\n1\n")
            (project_dir / "data" / "SCHEMA.md").write_text("schema")
        return str(project_dir)

    monkeypatch.setattr(new_command, "check_competition_access", access)
    monkeypatch.setattr(cli, "check_kaggle_cli", lambda: None)
    monkeypatch.setattr(new_command, "create_project", fake_create_project)
    state["config"] = config
    state["root"] = tmp_path
    return state


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict]:
    code = new_command.run_new([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_creates_workspace_and_reports_json(env: dict, capsys: pytest.CaptureFixture[str]) -> None:
    code, result = _run(capsys, "titanic")

    assert code == 0
    assert result["status"] == "created"
    assert result["title"] == "Titanic - ML from Disaster"
    assert result["path"] == str(env["root"] / "titanic")
    assert result["files"]["agents"] == "AGENTS.md"
    assert result["files"]["schema"] == "data/SCHEMA.md"
    assert result["added"] == ["AGENTS.md", "CLAUDE.md", "data/SCHEMA.md", "notes.md"]
    assert result["data_files_added"] == 1
    assert env["calls"][0]["details"].title == "Titanic - ML from Disaster"
    assert result["next_steps"] == [f"cd {env['root'] / 'titanic'}", "Read AGENTS.md"]
    assert env["calls"][0]["download_files"] is True
    assert env["calls"][0]["competition"].title == "Titanic - ML from Disaster"


def test_existing_project_stops_without_force(
    env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    (env["root"] / "titanic").mkdir()
    (env["root"] / "titanic" / "notes.md").write_text("mine")

    code, result = _run(capsys, "titanic")

    assert code == new_command.EXIT_EXISTS
    assert result["status"] == "exists"
    assert env["calls"] == []


def test_force_adds_only_missing_files(env: dict, capsys: pytest.CaptureFixture[str]) -> None:
    (env["root"] / "titanic").mkdir()
    (env["root"] / "titanic" / "notes.md").write_text("mine")

    code, result = _run(capsys, "titanic", "--force", "--no-download")

    assert code == 0
    assert result["status"] == "updated"
    assert result["added"] == ["AGENTS.md", "CLAUDE.md"]
    assert result["files"]["schema"] is None
    assert (env["root"] / "titanic" / "notes.md").read_text() == "mine"


def test_access_denied_reports_needs_join(env: dict, capsys: pytest.CaptureFixture[str]) -> None:
    env["access"] = (False, "403 Client Error: Forbidden")

    code, result = _run(capsys, "titanic")

    assert code == new_command.EXIT_NEEDS_JOIN
    assert result["status"] == "needs_join"
    assert result["url"] == "https://www.kaggle.com/competitions/titanic/rules"
    assert env["calls"] == []


def test_download_forbidden_during_creation_reports_needs_join(
    env: dict,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(**kwargs: object) -> str:
        raise ProjectCreationError("Download failed for titanic: 403 Forbidden")

    monkeypatch.setattr(new_command, "create_project", forbidden)

    code, result = _run(capsys, "titanic")

    assert code == new_command.EXIT_NEEDS_JOIN
    assert result["status"] == "needs_join"


def test_other_access_failures_are_errors(env: dict, capsys: pytest.CaptureFixture[str]) -> None:
    env["access"] = (False, "Unable to run kaggle access check")

    code, result = _run(capsys, "titanic")

    assert code == new_command.EXIT_ERROR
    assert result == {
        "slug": "titanic",
        "path": str(env["root"] / "titanic"),
        "title": "Titanic - ML from Disaster",
        "status": "error",
        "message": "Unable to run kaggle access check",
    }


def test_flags_skip_download_git_and_venv(env: dict, capsys: pytest.CaptureFixture[str]) -> None:
    code, _ = _run(capsys, "titanic", "--no-download", "--no-git", "--no-venv")

    assert code == 0
    assert env["access_calls"] == 0
    call = env["calls"][0]
    assert call["download_files"] is False
    assert call["config"].auto_git is False
    assert call["config"].auto_venv is False
    assert call["editor"] is None


def test_unknown_editor_is_an_error(
    env: dict,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Config,
        "available_editors",
        lambda self: [{"key": "code", "cmd": "code", "name": "VS Code"}],
    )

    code, result = _run(capsys, "titanic", "--editor", "vim")

    assert code == new_command.EXIT_ERROR
    assert result["message"] == "Editor 'vim' is not installed. Available: code"
    assert env["calls"] == []


def test_known_editor_is_passed_through(
    env: dict,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Config,
        "available_editors",
        lambda self: [{"key": "jupyter", "cmd": "jupyter-lab", "name": "Jupyter Lab"}],
    )

    code, _ = _run(capsys, "titanic", "--editor", "jupyter")

    assert code == 0
    assert env["calls"][0]["editor"] == "jupyter-lab"


@pytest.mark.parametrize(
    "value",
    [
        "titanic",
        "https://www.kaggle.com/competitions/titanic/",
        "https://www.kaggle.com/competitions/titanic/overview",
        "https://www.kaggle.com/competitions/titanic/rules?tab=x#top",
        "www.kaggle.com/c/titanic/data",
    ],
)
def test_competition_urls_resolve_to_slug(
    env: dict, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    code, result = _run(capsys, value)

    assert code == 0
    assert result["slug"] == "titanic"


@pytest.mark.parametrize(
    "value", ["..", "../outside", "..\\outside", "C:\\outside", "a b", ""]
)
def test_invalid_competition_is_rejected(
    env: dict, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    code, result = _run(capsys, value)

    assert code == new_command.EXIT_ERROR
    assert result["status"] == "error"
    assert env["calls"] == []


def test_missing_kaggle_cli_is_reported_before_any_work(
    env: dict, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli, "check_kaggle_cli", lambda: "kaggle CLI not found. Install with: pip install kaggle"
    )

    code, result = _run(capsys, "titanic", "--no-download")

    assert code == new_command.EXIT_ERROR
    assert result["message"] == "kaggle CLI not found. Install with: pip install kaggle"
    assert env["calls"] == []


def test_cancelled_creation_reports_cancelled(
    env: dict,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def cancelled(**kwargs: object) -> str:
        raise ProjectCreationCancelled("Project setup cancelled")

    monkeypatch.setattr(new_command, "create_project", cancelled)

    code, result = _run(capsys, "titanic")

    assert code == new_command.EXIT_CANCELLED
    assert result["status"] == "cancelled"


def test_ctrl_c_sets_cancel_and_waits_for_rollback(
    env: dict,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saw_cancel = threading.Event()

    def slow(**kwargs: object) -> str:
        if kwargs["cancel"].wait(timeout=5):  # type: ignore[attr-defined]
            saw_cancel.set()
        raise ProjectCreationCancelled("Project setup cancelled")

    monkeypatch.setattr(new_command, "create_project", slow)
    threading.Timer(0.3, _thread.interrupt_main).start()

    code, result = _run(capsys, "titanic")

    assert saw_cancel.is_set()
    assert code == new_command.EXIT_CANCELLED
    assert result["status"] == "cancelled"


def test_progress_goes_to_stderr_and_text_output_without_json(
    env: dict,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = new_command.run_new(["titanic"])

    captured = capsys.readouterr()
    assert code == 0
    assert "Fetching competition details..." in captured.err
    assert captured.out.splitlines()[0] == "created: Workspace ready."
    assert f"path: {env['root'] / 'titanic'}" in captured.out


def test_cli_dispatches_new_subcommand(
    env: dict,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["kag", "new", "titanic", "--json"])

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "created"
