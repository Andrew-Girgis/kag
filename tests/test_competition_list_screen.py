from __future__ import annotations

import pytest
from textual.widgets import Label

from kag.config import Config
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
    assert "could not load competitions" in text, (
        "Expected a clear remote-fetch failure message when Kaggle competition loading raises an exception."
    )
    assert "kag --doctor" in text, (
        "Expected troubleshooting guidance to be shown when remote competition loading fails."
    )
    assert "no competitions found" not in text
