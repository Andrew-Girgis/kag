from __future__ import annotations

import pytest

from kag.config import Config
from kag.kaggle_api import Competition
from kag.project import ProjectCreationError
from kag.screens.access_required import AccessRequiredScreen
from kag.screens.confirm_download import ConfirmDownloadScreen
from kag.screens.competition_list import CompetitionListScreen
from kag.screens.editor_select import EditorSelectScreen
from kag import screens
from kag import tui
from kag.tui import KagApp


def test_editor_selected_download_failure_does_not_set_result(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="forbidden-download",
        title="Forbidden Download",
        deadline="",
        reward="",
        team_count="0",
    )
    app = KagApp(Config(kag_path=tmp_path))
    notifications: list[str] = []
    pushed_screens: list[object] = []

    def failed_create_project(*args: object, **kwargs: object) -> str:
        raise ProjectCreationError("403 Client Error: Forbidden")

    monkeypatch.setattr(tui, "create_project", failed_create_project)
    monkeypatch.setattr(app, "notify", lambda message, **kwargs: notifications.append(message))
    monkeypatch.setattr(
        app, "push_screen", lambda screen, callback=None: pushed_screens.append(screen)
    )
    monkeypatch.setattr(app, "exit", lambda *args, **kwargs: None)

    app._on_editor_selected(
        EditorSelectScreen.Selected(
            competition=competition,
            download_files=True,
            editor=None,
        )
    )

    assert app.result is None
    assert notifications == ["403 Client Error: Forbidden"]
    assert pushed_screens, "Expected the TUI to return to the download choice after failure."


def test_download_confirmation_denied_access_pushes_access_required_screen(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="needs-rules",
        title="Needs Rules",
        deadline="",
        reward="",
        team_count="0",
    )
    app = KagApp(Config(kag_path=tmp_path))
    pushed_screens: list[object] = []

    monkeypatch.setattr(tui, "check_competition_access", lambda slug: (False, "403 Forbidden"))
    monkeypatch.setattr(
        app, "push_screen", lambda screen, callback=None: pushed_screens.append(screen)
    )

    app._on_download_confirmed(
        ConfirmDownloadScreen.Confirmed(competition=competition, download_files=True)
    )

    assert isinstance(pushed_screens[0], AccessRequiredScreen)
    assert app.result is None


def test_competition_selection_not_joined_pushes_access_required_before_download_prompt(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="needs-rules",
        title="Needs Rules",
        deadline="",
        reward="",
        team_count="0",
    )
    app = KagApp(Config(kag_path=tmp_path))
    pushed_screens: list[object] = []

    monkeypatch.setattr(
        tui,
        "check_competition_access",
        lambda slug: (_ for _ in ()).throw(AssertionError("access check should not run first")),
    )
    monkeypatch.setattr(
        app, "push_screen", lambda screen, callback=None: pushed_screens.append(screen)
    )

    app._on_competition_selected(CompetitionListScreen.Selected(competition=competition))

    assert isinstance(pushed_screens[0], AccessRequiredScreen)
    assert app.result is None


def test_competition_selection_access_success_pushes_download_prompt(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="has-access",
        title="Has Access",
        deadline="",
        reward="",
        team_count="0",
        is_joined=True,
    )
    app = KagApp(Config(kag_path=tmp_path))
    pushed_screens: list[object] = []

    monkeypatch.setattr(
        tui,
        "check_competition_access",
        lambda slug: (_ for _ in ()).throw(AssertionError("access check should not run first")),
    )
    monkeypatch.setattr(
        app, "push_screen", lambda screen, callback=None: pushed_screens.append(screen)
    )

    app._on_competition_selected(CompetitionListScreen.Selected(competition=competition))

    assert isinstance(pushed_screens[0], ConfirmDownloadScreen)


def test_download_confirmation_access_success_pushes_editor_screen(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="has-access",
        title="Has Access",
        deadline="",
        reward="",
        team_count="0",
    )
    app = KagApp(Config(kag_path=tmp_path))
    pushed_screens: list[object] = []

    monkeypatch.setattr(tui, "check_competition_access", lambda slug: (True, "Access confirmed"))
    monkeypatch.setattr(
        app, "push_screen", lambda screen, callback=None: pushed_screens.append(screen)
    )

    app._on_download_confirmed(
        ConfirmDownloadScreen.Confirmed(competition=competition, download_files=True)
    )

    assert isinstance(pushed_screens[0], EditorSelectScreen)


def test_access_required_join_opens_kaggle_and_retries_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="needs-rules",
        title="Needs Rules",
        deadline="",
        reward="",
        team_count="0",
    )
    screen = AccessRequiredScreen(competition, "403 Forbidden")
    opened_pages: list[tuple[str, str]] = []
    dismissed: list[AccessRequiredScreen.Resolved | None] = []

    monkeypatch.setattr(
        screens.access_required,
        "open_competition_page",
        lambda slug, page: opened_pages.append((slug, page)),
    )
    monkeypatch.setattr(
        screens.access_required,
        "check_competition_access",
        lambda slug: (True, "Access confirmed"),
    )
    monkeypatch.setattr(screen, "dismiss", lambda result=None: dismissed.append(result))

    screen.on_list_view_selected(
        type("Event", (), {"item": type("Item", (), {"id": "opt-join"})()})()
    )

    assert opened_pages == [("needs-rules", "overview"), ("needs-rules", "rules")]
    assert dismissed
    assert dismissed[0] is not None
    assert dismissed[0].download_files is True
    assert competition.is_joined is True


def test_access_required_already_joined_retries_without_opening_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="needs-rules",
        title="Needs Rules",
        deadline="",
        reward="",
        team_count="0",
    )
    screen = AccessRequiredScreen(competition, "403 Forbidden")
    opened_pages: list[tuple[str, str]] = []
    dismissed: list[AccessRequiredScreen.Resolved | None] = []

    monkeypatch.setattr(
        screens.access_required,
        "open_competition_page",
        lambda slug, page: opened_pages.append((slug, page)),
    )
    monkeypatch.setattr(
        screens.access_required,
        "check_competition_access",
        lambda slug: (True, "Access confirmed"),
    )
    monkeypatch.setattr(screen, "dismiss", lambda result=None: dismissed.append(result))

    screen.on_list_view_selected(
        type("Event", (), {"item": type("Item", (), {"id": "opt-already-joined"})()})()
    )

    assert opened_pages == []
    assert dismissed
    assert dismissed[0] is not None
    assert dismissed[0].download_files is True
    assert competition.is_joined is True


def test_access_required_retry_success_dismisses_to_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="needs-rules",
        title="Needs Rules",
        deadline="",
        reward="",
        team_count="0",
    )
    screen = AccessRequiredScreen(competition, "403 Forbidden")
    dismissed: list[AccessRequiredScreen.Resolved | None] = []

    monkeypatch.setattr(
        screens.access_required,
        "check_competition_access",
        lambda slug: (True, "Access confirmed"),
    )
    monkeypatch.setattr(screen, "dismiss", lambda result=None: dismissed.append(result))

    screen._retry_access()

    assert dismissed
    assert dismissed[0] is not None
    assert dismissed[0].download_files is True


def test_access_required_retry_failure_preserves_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="needs-rules",
        title="Needs Rules",
        deadline="",
        reward="",
        team_count="0",
    )
    screen = AccessRequiredScreen(competition, "403 Forbidden")
    dismissed: list[object] = []

    monkeypatch.setattr(
        screens.access_required,
        "check_competition_access",
        lambda slug: (False, "still forbidden"),
    )
    monkeypatch.setattr(screen, "dismiss", lambda result=None: dismissed.append(result))
    monkeypatch.setattr(
        screen, "query_one", lambda *args, **kwargs: (_ for _ in ()).throw(Exception())
    )

    screen._retry_access()

    assert dismissed == []
    assert screen.details == "still forbidden"


def test_access_required_skip_download_dismisses_without_download() -> None:
    competition = Competition(
        slug="needs-rules",
        title="Needs Rules",
        deadline="",
        reward="",
        team_count="0",
    )
    screen = AccessRequiredScreen(competition, "403 Forbidden")
    dismissed: list[AccessRequiredScreen.Resolved | None] = []

    screen.dismiss = lambda result=None: dismissed.append(result)  # type: ignore[method-assign]

    screen.on_list_view_selected(
        type("Event", (), {"item": type("Item", (), {"id": "opt-skip"})()})()
    )

    assert dismissed
    assert dismissed[0] is not None
    assert dismissed[0].download_files is False
    assert competition.is_joined is False
