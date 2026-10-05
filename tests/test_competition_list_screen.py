from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Input, Label, ListView

from kag.config import Config
from kag.kaggle_api import Competition
from kag.screens import competition_list
from kag.tui import KagApp


def _label_texts(app: KagApp) -> list[str]:
    return [str(label.render()) for label in app.screen.query(Label)]


@pytest.mark.asyncio
async def test_remote_failure_keeps_local_projects_and_shows_guidance(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "titanic").mkdir()

    def failed_remote_fetch(*args: object, **kwargs: object) -> object:
        raise RuntimeError("offline")

    monkeypatch.setattr(competition_list, "list_entered_competitions", failed_remote_fetch)
    monkeypatch.setattr(competition_list, "list_competitions_page", failed_remote_fetch)

    app = KagApp(Config(kag_path=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause(0.5)

        text = "\n".join(_label_texts(app)).lower()

    assert "titanic" in text
    assert "kaggle competitions unavailable" in text, (
        "Expected a clear remote-fetch failure message when Kaggle competition loading raises an exception."
    )
    assert "local notebooks are still available" in text
    assert "kag doctor" in text, (
        "Expected troubleshooting guidance to be shown when remote competition loading fails."
    )
    assert "no competitions found" not in text


def _highlighted(app: KagApp) -> list[str]:
    results = app.screen.query_one("#results", ListView)
    return [child.id or "" for child in results.children if child.has_class("-highlight")]


@pytest.mark.asyncio
async def test_only_one_row_highlighted_after_loading_more(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def competitions(start: int, count: int) -> list[Competition]:
        return [
            Competition(f"comp-{i}", f"Comp {i}", "2030-01-01", "Knowledge", "1")
            for i in range(start, start + count)
        ]

    def list_page(**kwargs: object) -> tuple[list[Competition], bool]:
        if kwargs.get("page", 1) == 1:
            return competitions(0, 20), True
        return competitions(20, 5), False

    monkeypatch.setattr(competition_list, "list_entered_competitions", lambda: [])
    monkeypatch.setattr(competition_list, "list_competitions_page", list_page)
    app = KagApp(Config(kag_path=tmp_path))

    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause(0.5)
        for _ in range(26):
            await pilot.press("down")
        await pilot.pause(1.5)
        for _ in range(3):
            await pilot.press("down")
        await pilot.pause(0.2)

        results = app.screen.query_one("#results", ListView)
        assert len(_highlighted(app)) == 1
        assert _highlighted(app)[0] == results.highlighted_child.id


@pytest.mark.asyncio
async def test_only_one_row_highlighted_after_search_rerender(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(competition_list, "list_entered_competitions", lambda: [])
    monkeypatch.setattr(
        competition_list,
        "list_competitions_page",
        lambda **kwargs: (
            [Competition(f"comp-{i}", f"Comp {i}", "", "", "1") for i in range(10)],
            False,
        ),
    )
    app = KagApp(Config(kag_path=tmp_path))

    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause(0.5)
        for _ in range(5):
            await pilot.press("down")
        app.screen.query_one("#search", Input).focus()
        await pilot.press("c", "o", "m", "p")
        await pilot.pause(0.3)
        await pilot.press("down", "down", "down")
        await pilot.pause(0.2)

        assert len(_highlighted(app)) == 1
