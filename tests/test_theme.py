from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from textual.widgets import Input, ListView

from kag import cli, tui
from kag.config import Config, save_theme
from kag.screens import competition_list
from kag.screens.competition_list import RowLabel
from kag.theme import resolve_theme, theme_names
from kag.tui import KagApp, ThemeProvider


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("KAG_THEME", raising=False)
    monkeypatch.delenv("KAG_PATH", raising=False)
    return tmp_path


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("terminal", "textual-ansi"),
        ("kag", "textual-dark"),
        (" Nord ", "nord"),
        ("catppuccin-mocha", "catppuccin-mocha"),
        ("textual-ansi", "textual-ansi"),
    ],
)
def test_resolve_theme_accepts_aliases_and_builtins(name: str, expected: str) -> None:
    assert resolve_theme(name) == (expected, None)


def test_unknown_theme_falls_back_to_terminal_with_a_warning() -> None:
    textual_name, warning = resolve_theme("nrod")

    assert textual_name == "textual-ansi"
    assert warning is not None
    assert "'nrod'" in warning and "using terminal" in warning and "nord" in warning


def test_theme_names_lead_with_terminal_and_kag() -> None:
    names = theme_names()

    assert names[:2] == ["terminal", "kag"]
    assert "textual-ansi" not in names and "textual-dark" not in names
    assert "nord" in names


def test_config_theme_defaults_to_terminal(home: Path) -> None:
    config = Config.load()

    assert (config.theme, config.theme_source) == ("terminal", "default")


def test_config_theme_from_file_and_env_override(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (home / ".kag_config.toml").write_text('theme = "nord"\n')
    assert (Config.load().theme, Config.load().theme_source) == ("nord", "config")

    monkeypatch.setenv("KAG_THEME", "gruvbox")
    assert (Config.load().theme, Config.load().theme_source) == ("gruvbox", "KAG_THEME")


def test_save_theme_creates_the_config_file(tmp_path: Path) -> None:
    path = tmp_path / ".kag_config.toml"

    save_theme("nord", path)

    assert tomllib.loads(path.read_text()) == {"theme": "nord"}


def test_save_theme_replaces_only_the_top_level_theme(tmp_path: Path) -> None:
    path = tmp_path / ".kag_config.toml"
    path.write_text(
        '# my settings\nkag_path = "/data/kaggle"\ntheme = "kag"\n\n'
        '[environment]\ninstall = "always"\ntheme = "untouched"\n'
    )

    save_theme("terminal", path)

    data = tomllib.loads(path.read_text())
    assert data["theme"] == "terminal"
    assert data["kag_path"] == "/data/kaggle"
    assert data["environment"] == {"install": "always", "theme": "untouched"}
    assert path.read_text().startswith("# my settings\n")


def test_save_theme_inserts_before_the_first_table(tmp_path: Path) -> None:
    path = tmp_path / ".kag_config.toml"
    path.write_text('auto_git = false\n[environment]\ninstall = "never"\n')

    save_theme("dracula", path)

    data = tomllib.loads(path.read_text())
    assert data == {"auto_git": False, "theme": "dracula", "environment": {"install": "never"}}


@pytest.mark.parametrize(
    ("theme", "expected"),
    [("terminal", "textual-ansi"), ("kag", "textual-dark"), ("nord", "nord")],
)
def test_app_starts_with_the_configured_theme(tmp_path: Path, theme: str, expected: str) -> None:
    app = KagApp(Config(kag_path=tmp_path, theme=theme))

    assert app.theme == expected
    assert app.messages == []


def test_app_warns_about_an_unknown_theme(tmp_path: Path) -> None:
    app = KagApp(Config(kag_path=tmp_path, theme="nrod"))

    assert app.theme == "textual-ansi"
    assert len(app.messages) == 1 and "'nrod'" in app.messages[0]


def test_choosing_a_theme_applies_and_saves_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved: list[str] = []
    notes: list[str] = []
    monkeypatch.setattr(tui, "save_theme", lambda name: saved.append(name) or tmp_path / "c")
    app = KagApp(Config(kag_path=tmp_path, theme="nord", theme_source="KAG_THEME"))
    monkeypatch.setattr(app, "notify", lambda message, **kwargs: notes.append(message))

    app.choose_theme("terminal")

    assert app.theme == "textual-ansi"
    assert saved == ["terminal"]
    assert "KAG_THEME is set" in notes[0]


@pytest.mark.asyncio
async def test_theme_command_is_offered_in_terminal_mode(tmp_path: Path, stub_lists: None) -> None:
    app = KagApp(Config(kag_path=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        titles = [command.title for command in app.get_system_commands(app.screen)]

    assert app.ansi_color is True
    assert titles[0] == "Theme"
    assert titles.count("Theme") == 1


def test_theme_provider_lists_terminal_first() -> None:
    provider = ThemeProvider.__new__(ThemeProvider)

    names = [name for _, name in provider.commands]

    assert names == theme_names()


@pytest.fixture
def stub_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    from kag.kaggle_api import Competition

    joined = Competition(
        slug="titanic",
        title="Titanic",
        deadline="2030",
        reward="Knowledge",
        team_count="1",
        is_joined=True,
    )
    monkeypatch.setattr(competition_list, "list_entered_competitions", lambda: [joined])
    monkeypatch.setattr(competition_list, "list_competitions_page", lambda **kw: ([], False))


@pytest.mark.asyncio
async def test_terminal_mode_has_no_fills_and_a_readable_selection(
    tmp_path: Path, stub_lists: None
) -> None:
    app = KagApp(Config(kag_path=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause(0.3)
        helpbar = app.screen.query_one("#helpbar")
        assert helpbar.styles.text_style.dim
        assert helpbar.styles.border_top[0] in ("", "none")
        app.screen.query_one("#search", Input).focus()
        await pilot.press("down")
        await pilot.pause(0.1)
        results = app.screen.query_one("#results", ListView)
        label = results.highlighted_child.query_one(RowLabel)
        assert label.render().spans == []
        assert label.render().plain == label.colored.plain
        app.screen.query_one("#search", Input).focus()
        await pilot.pause(0.1)
        assert label.render().spans == []


@pytest.mark.asyncio
async def test_other_themes_keep_row_colours(tmp_path: Path, stub_lists: None) -> None:
    app = KagApp(Config(kag_path=tmp_path, theme="kag"))

    async with app.run_test() as pilot:
        await pilot.pause(0.3)
        app.screen.query_one("#search", Input).focus()
        await pilot.press("down")
        await pilot.pause(0.1)
        results = app.screen.query_one("#results", ListView)
        label = results.highlighted_child.query_one(RowLabel)
        assert label.render() is label.colored


def test_doctor_reports_the_theme(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("KAG_THEME", "nrod")
    monkeypatch.setattr(cli, "bundled_kaggle_available", lambda: False)
    monkeypatch.setattr(cli, "_kaggle_auth_status", lambda: (True, "ok"))
    monkeypatch.setattr(cli.kaggle_sdk, "sdk_version", lambda: "2.2.4")
    monkeypatch.setattr(cli, "RESULT_FILE", home / ".kag_result")

    cli.doctor_command(json_output=True)

    checks = {c["name"]: c for c in json.loads(capsys.readouterr().out)["checks"]}
    assert checks["theme"]["status"] == "warn"
    assert "'nrod'" in checks["theme"]["details"]
