from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Input, ListView

from kag.config import Config
from kag.kaggle_api import Competition, CompetitionFile, FileListResult
from kag.screens import competition_list, confirm_download, existing_project
from kag.screens.access_required import AccessRequiredScreen
from kag.screens.competition_list import CompetitionListScreen
from kag.screens.confirm_download import ConfirmDownloadScreen
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
