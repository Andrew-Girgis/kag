from __future__ import annotations

import pytest

from kag import cli


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
