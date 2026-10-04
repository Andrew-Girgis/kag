from __future__ import annotations

import threading
from pathlib import Path

import pytest
from textual.widgets import Input, ListView

from kag.config import Config
from kag.kaggle_api import Competition, CompetitionFile, FileListResult
from kag.project import ProjectCreationCancelled
from kag.screens import (
    access_required,
    competition_list,
    confirm_download,
    creating_project,
    existing_project,
)
from kag.screens.access_required import AccessRequiredScreen
from kag.screens.competition_list import CompetitionListScreen
from kag.screens.confirm_download import ConfirmDownloadScreen
from kag.screens.creating_project import CreatingProjectScreen
from kag.screens.editor_select import EditorSelectScreen
from kag.screens.existing_project import ExistingProjectScreen
from kag.tui import KagApp


def _joined() -> Competition:
    return Competition(
        slug="titanic",
        title="Titanic",
        deadline="2030-01-01",
        reward="Knowledge",
        team_count="10",
    )


def _not_joined() -> Competition:
    return Competition(
        slug="tabular-tide",
        title="Tabular Tide",
        deadline="2030-01-01",
        reward="$1,000",
        team_count="5",
    )


@pytest.fixture
def stub_kaggle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(competition_list, "list_entered_competitions", lambda: [_joined()])
    monkeypatch.setattr(
        competition_list,
        "list_competitions_page",
        lambda **kwargs: ([_not_joined()], False),
    )
    monkeypatch.setattr(
        confirm_download,
        "list_competition_files",
        lambda slug: FileListResult(True, (CompetitionFile("train.csv", 10),)),
    )


def _highlighted_slug(app: KagApp) -> str | None:
    screen = app.screen
    assert isinstance(screen, CompetitionListScreen)
    item = screen.query_one("#results", ListView).highlighted_child
    selected = screen._item_lookup.get(item.id) if item is not None and item.id else None
    return getattr(selected, "slug", None)


@pytest.mark.asyncio
async def test_escape_from_download_prompt_returns_to_picker_with_search(
    tmp_path: Path,
    stub_kaggle: None,
) -> None:
    app = KagApp(Config(kag_path=tmp_path), initial_query="tita")

    async with app.run_test() as pilot:
        await pilot.pause(0.3)
        app.screen.query_one("#search", Input).focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ConfirmDownloadScreen)

        await pilot.press("escape")
        await pilot.pause(0.2)

        assert isinstance(app.screen, CompetitionListScreen)
        assert app.screen.query_one("#search", Input).value == "tita"
        assert _highlighted_slug(app) == "titanic"


@pytest.mark.asyncio
async def test_escape_from_access_required_returns_to_picker(
    tmp_path: Path,
    stub_kaggle: None,
) -> None:
    app = KagApp(Config(kag_path=tmp_path), initial_query="tide")

    async with app.run_test() as pilot:
        await pilot.pause(0.3)
        app.screen.query_one("#search", Input).focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, AccessRequiredScreen)

        await pilot.press("escape")
        await pilot.pause(0.2)

        assert isinstance(app.screen, CompetitionListScreen)
        assert app.screen.query_one("#search", Input).value == "tide"
        assert _highlighted_slug(app) == "tabular-tide"


@pytest.mark.asyncio
async def test_escape_from_editor_select_returns_to_picker(
    tmp_path: Path,
    stub_kaggle: None,
) -> None:
    app = KagApp(Config(kag_path=tmp_path), initial_query="tita")

    async with app.run_test() as pilot:
        await pilot.pause(0.3)
        app.screen.query_one("#search", Input).focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ConfirmDownloadScreen)

        await pilot.press("down", "enter")
        await pilot.pause(0.2)
        assert isinstance(app.screen, EditorSelectScreen)

        await pilot.press("escape")
        await pilot.pause(0.2)

        assert isinstance(app.screen, CompetitionListScreen)
        assert _highlighted_slug(app) == "titanic"


@pytest.mark.asyncio
async def test_escape_on_picker_still_quits(tmp_path: Path, stub_kaggle: None) -> None:
    app = KagApp(Config(kag_path=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause(0.3)
        await pilot.press("escape")
        await pilot.pause(0.1)

        assert app.return_code is not None or not app.is_running


def _make_existing_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "titanic"
    project_dir.mkdir()
    (project_dir / "titanic.ipynb").write_text("MY NOTEBOOK")
    return project_dir


@pytest.mark.asyncio
async def test_existing_project_open_exits_into_folder(tmp_path: Path, stub_kaggle: None) -> None:
    project_dir = _make_existing_project(tmp_path)
    app = KagApp(Config(kag_path=tmp_path), initial_query="tita")

    async with app.run_test() as pilot:
        await pilot.pause(0.3)
        app.screen.query_one("#search", Input).focus()
        await pilot.press("down")
        await pilot.pause(0.1)
        _focus_remote_item(app, "titanic")
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert isinstance(app.screen, ExistingProjectScreen)

        await pilot.press("enter")
        await pilot.pause(0.2)

    assert app.result == str(project_dir)
    assert (project_dir / "titanic.ipynb").read_text() == "MY NOTEBOOK"


@pytest.mark.asyncio
async def test_existing_project_fill_continues_to_download_prompt(
    tmp_path: Path,
    stub_kaggle: None,
) -> None:
    _make_existing_project(tmp_path)
    app = KagApp(Config(kag_path=tmp_path), initial_query="tita")

    async with app.run_test() as pilot:
        await pilot.pause(0.3)
        app.screen.query_one("#search", Input).focus()
        await pilot.press("down")
        await pilot.pause(0.1)
        _focus_remote_item(app, "titanic")
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert isinstance(app.screen, ExistingProjectScreen)

        await pilot.press("down", "enter")
        await pilot.pause(0.3)

        assert isinstance(app.screen, ConfirmDownloadScreen)


@pytest.mark.asyncio
async def test_escape_from_existing_project_returns_to_picker(
    tmp_path: Path,
    stub_kaggle: None,
) -> None:
    _make_existing_project(tmp_path)
    app = KagApp(Config(kag_path=tmp_path), initial_query="tita")

    async with app.run_test() as pilot:
        await pilot.pause(0.3)
        app.screen.query_one("#search", Input).focus()
        await pilot.press("down")
        await pilot.pause(0.1)
        _focus_remote_item(app, "titanic")
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert isinstance(app.screen, ExistingProjectScreen)

        await pilot.press("escape")
        await pilot.pause(0.2)

        assert isinstance(app.screen, CompetitionListScreen)
        assert app.screen.query_one("#search", Input).value == "tita"


def _focus_remote_item(app: KagApp, slug: str) -> None:
    screen = app.screen
    assert isinstance(screen, CompetitionListScreen)
    results = screen.query_one("#results", ListView)
    for index, child in enumerate(results.children):
        selected = screen._item_lookup.get(child.id or "")
        if isinstance(selected, Competition) and selected.slug == slug:
            results.index = index
            results.focus()
            return
    raise AssertionError(f"{slug} not found in picker results")


def test_describe_data_dir_caps_file_count(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"

    assert existing_project._describe_data_dir(data_dir) == "missing"
    data_dir.mkdir()
    assert existing_project._describe_data_dir(data_dir) == "empty"
    for index in range(3):
        (data_dir / f"{index}.csv").write_text("x")
    assert existing_project._describe_data_dir(data_dir) == "3 files"

    for index in range(existing_project.DATA_FILE_COUNT_LIMIT + 5):
        (data_dir / f"extra_{index}.csv").write_text("x")
    assert (
        existing_project._describe_data_dir(data_dir)
        == f"{existing_project.DATA_FILE_COUNT_LIMIT}+ files"
    )


@pytest.mark.asyncio
async def test_access_retry_runs_off_the_ui_thread(
    tmp_path: Path,
    stub_kaggle: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_threads: list[threading.Thread] = []

    def record_check(slug: str) -> tuple[bool, str]:
        check_threads.append(threading.current_thread())
        return True, "Access confirmed"

    monkeypatch.setattr(access_required, "check_competition_access", record_check)
    app = KagApp(Config(kag_path=tmp_path), initial_query="tide")

    async with app.run_test() as pilot:
        await pilot.pause(0.3)
        app.screen.query_one("#search", Input).focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.2)
        assert isinstance(app.screen, AccessRequiredScreen)

        await pilot.press("down", "enter")
        await pilot.pause(0.3)

        assert check_threads
        assert check_threads[0] is not threading.main_thread()
        assert isinstance(app.screen, ConfirmDownloadScreen)


@pytest.mark.asyncio
async def test_download_confirm_checks_access_in_background_when_listing_failed(
    tmp_path: Path,
    stub_kaggle: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_threads: list[threading.Thread] = []

    def record_check(slug: str) -> tuple[bool, str]:
        check_threads.append(threading.current_thread())
        return False, "403 Forbidden"

    monkeypatch.setattr(
        confirm_download,
        "list_competition_files",
        lambda slug: FileListResult(False, details="403 Forbidden"),
    )
    monkeypatch.setattr(confirm_download, "check_competition_access", record_check)
    app = KagApp(Config(kag_path=tmp_path), initial_query="tita")

    async with app.run_test() as pilot:
        await pilot.pause(0.3)
        app.screen.query_one("#search", Input).focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ConfirmDownloadScreen)

        await pilot.press("enter")
        await pilot.pause(0.3)

        assert check_threads
        assert check_threads[0] is not threading.main_thread()
        assert isinstance(app.screen, AccessRequiredScreen)
        assert app.screen.details == "403 Forbidden"


@pytest.mark.asyncio
async def test_download_confirm_reuses_successful_file_listing(
    tmp_path: Path,
    stub_kaggle: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(slug: str) -> tuple[bool, str]:
        raise AssertionError("listing already confirmed access")

    monkeypatch.setattr(confirm_download, "check_competition_access", fail_if_called)
    app = KagApp(Config(kag_path=tmp_path), initial_query="tita")

    async with app.run_test() as pilot:
        await pilot.pause(0.3)
        app.screen.query_one("#search", Input).focus()
        await pilot.press("down", "enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ConfirmDownloadScreen)

        await pilot.press("enter")
        await pilot.pause(0.2)

        assert isinstance(app.screen, EditorSelectScreen)


async def _reach_editor_select(app: KagApp, pilot: object) -> None:
    await pilot.pause(0.3)  # type: ignore[attr-defined]
    app.screen.query_one("#search", Input).focus()
    await pilot.press("down", "enter")  # type: ignore[attr-defined]
    await pilot.pause(0.3)  # type: ignore[attr-defined]
    assert isinstance(app.screen, ConfirmDownloadScreen)
    await pilot.press("enter")  # type: ignore[attr-defined]
    await pilot.pause(0.2)  # type: ignore[attr-defined]
    assert isinstance(app.screen, EditorSelectScreen)


def _select_terminal_only(app: KagApp) -> None:
    editors = app.screen.query_one("#editor-list", ListView)
    for index, child in enumerate(editors.children):
        if child.id == "editor-none":
            editors.index = index
    editors.focus()


@pytest.mark.asyncio
async def test_project_creation_runs_in_background_and_exits_into_project(
    tmp_path: Path,
    stub_kaggle: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker_threads: list[threading.Thread] = []
    seen_status: list[str] = []

    def fake_create_project(**kwargs: object) -> str:
        worker_threads.append(threading.current_thread())
        kwargs["progress"]("Downloading data... 1.0 MB")  # type: ignore[operator]
        return str(tmp_path / "titanic")

    monkeypatch.setattr(creating_project, "create_project", fake_create_project)
    app = KagApp(Config(kag_path=tmp_path), initial_query="tita")
    original_set_status = creating_project.CreatingProjectScreen._set_status

    def record_status(self: creating_project.CreatingProjectScreen, message: str) -> None:
        seen_status.append(message)
        original_set_status(self, message)

    monkeypatch.setattr(creating_project.CreatingProjectScreen, "_set_status", record_status)

    async with app.run_test() as pilot:
        await _reach_editor_select(app, pilot)
        _select_terminal_only(app)
        await pilot.press("enter")
        await pilot.pause(0.5)

    assert worker_threads and worker_threads[0] is not threading.main_thread()
    assert "Downloading data... 1.0 MB" in seen_status
    assert app.result == str(tmp_path / "titanic")


@pytest.mark.asyncio
async def test_escape_cancels_project_creation_and_returns_to_picker(
    tmp_path: Path,
    stub_kaggle: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = threading.Event()

    def slow_create_project(**kwargs: object) -> str:
        cancel = kwargs["cancel"]
        started.set()
        assert cancel.wait(timeout=5)  # type: ignore[attr-defined]
        raise ProjectCreationCancelled("Project setup cancelled")

    monkeypatch.setattr(creating_project, "create_project", slow_create_project)
    app = KagApp(Config(kag_path=tmp_path), initial_query="tita")

    async with app.run_test() as pilot:
        await _reach_editor_select(app, pilot)
        _select_terminal_only(app)
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert started.is_set()
        assert isinstance(app.screen, CreatingProjectScreen)

        await pilot.press("escape")
        await pilot.pause(0.4)

        assert isinstance(app.screen, CompetitionListScreen)
        assert app.result is None


@pytest.mark.asyncio
async def test_project_creation_error_returns_to_download_prompt(
    tmp_path: Path,
    stub_kaggle: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_create_project(**kwargs: object) -> str:
        raise OSError("No space left on device")

    monkeypatch.setattr(creating_project, "create_project", broken_create_project)
    app = KagApp(Config(kag_path=tmp_path), initial_query="tita")

    async with app.run_test() as pilot:
        await _reach_editor_select(app, pilot)
        _select_terminal_only(app)
        await pilot.press("enter")
        await pilot.pause(0.4)

        assert isinstance(app.screen, ConfirmDownloadScreen)
        assert app.result is None
