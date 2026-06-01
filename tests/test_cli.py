from __future__ import annotations

import pytest

from kag import cli


def test_help_output_does_not_require_kaggle(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_if_called() -> str | None:
        raise AssertionError("help should not check Kaggle setup")

    monkeypatch.setattr(cli.sys, "argv", ["kag", "--help"])
    monkeypatch.setattr(cli, "check_kaggle_cli", fail_if_called)

    cli.main()

    captured = capsys.readouterr()
    assert captured.out == cli.HELP_TEXT + "\n"
    assert captured.err == ""


def test_short_help_matches_long_help(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_if_called() -> str | None:
        raise AssertionError("help should not check Kaggle setup")

    monkeypatch.setattr(cli.sys, "argv", ["kag", "-h"])
    monkeypatch.setattr(cli, "check_kaggle_cli", fail_if_called)

    cli.main()

    assert capsys.readouterr().out == cli.HELP_TEXT + "\n"


def test_help_takes_precedence_over_search_query(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("help should not launch the TUI")

    monkeypatch.setattr(cli.sys, "argv", ["kag", "--help", "titanic"])
    monkeypatch.setattr(cli, "check_kaggle_cli", lambda: None)
    monkeypatch.setattr(cli, "Config", fail_if_called)

    cli.main()

    assert capsys.readouterr().out == cli.HELP_TEXT + "\n"


def test_version_output_is_not_mixed_with_update_notice(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["kag", "--version"])

    cli.main()

    assert capsys.readouterr().out == "kag 0.1.0\n"


def test_init_output_is_shell_code_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["kag", "--init"])

    cli.main()

    output = capsys.readouterr().out
    assert output.startswith("kag() {")
    assert "Update available" not in output
    assert "is available" not in output
