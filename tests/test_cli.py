from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kag import __version__, cli


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

    assert capsys.readouterr().out == f"kag {__version__}\n"


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


@pytest.fixture
def kaggle_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in (
        "KAGGLE_API_TOKEN",
        "KAGGLE_USERNAME",
        "KAGGLE_KEY",
        "KAGGLE_CONFIG_DIR",
        "XDG_CONFIG_HOME",
        "KAG_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_auth_status_reports_missing_credentials(kaggle_home: Path) -> None:
    ok, details = cli._kaggle_auth_status()

    assert ok is False
    assert "kaggle auth login" in details


def test_auth_status_rejects_empty_kaggle_json(kaggle_home: Path) -> None:
    _write(kaggle_home / ".kaggle" / "kaggle.json", "")

    ok, details = cli._kaggle_auth_status()

    assert ok is False
    assert "empty or not valid JSON" in details


def test_auth_status_rejects_kaggle_json_without_key(kaggle_home: Path) -> None:
    _write(kaggle_home / ".kaggle" / "kaggle.json", '{"username": "someone"}')

    ok, details = cli._kaggle_auth_status()

    assert ok is False
    assert "missing username or key" in details


def test_auth_status_accepts_valid_kaggle_json(kaggle_home: Path) -> None:
    _write(kaggle_home / ".kaggle" / "kaggle.json", '{"username": "someone", "key": "abc"}')

    ok, details = cli._kaggle_auth_status()

    assert ok is True
    assert details.endswith("(legacy)")


def test_auth_status_respects_kaggle_config_dir(
    kaggle_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = kaggle_home / "custom-kaggle"
    _write(config_dir / "kaggle.json", '{"username": "someone", "key": "abc"}')
    monkeypatch.setenv("KAGGLE_CONFIG_DIR", str(config_dir))

    ok, details = cli._kaggle_auth_status()

    assert ok is True
    assert str(config_dir / "kaggle.json") in details


@pytest.mark.parametrize("token_name", ["access_token", "access_token.txt"])
def test_auth_status_accepts_access_token_file(kaggle_home: Path, token_name: str) -> None:
    _write(kaggle_home / ".kaggle" / token_name, "token-value\n")

    ok, details = cli._kaggle_auth_status()

    assert ok is True
    assert details == str(kaggle_home / ".kaggle" / token_name)


def test_auth_status_accepts_oauth_login_even_with_empty_kaggle_json(kaggle_home: Path) -> None:
    _write(kaggle_home / ".kaggle" / "kaggle.json", "")
    _write(kaggle_home / ".kaggle" / "credentials.json", '{"refresh_token": "x"}')

    ok, details = cli._kaggle_auth_status()

    assert ok is True
    assert "kaggle auth login" in details


def test_auth_status_accepts_environment_credentials(
    kaggle_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KAGGLE_USERNAME", "someone")
    monkeypatch.setenv("KAGGLE_KEY", "abc")

    assert cli._kaggle_auth_status() == (True, "KAGGLE_USERNAME + KAGGLE_KEY")


@pytest.mark.parametrize(
    ("file_values", "env", "expected_suffix"),
    [
        ('{"username": "someone"}', {"KAGGLE_KEY": "abc"}, "+ KAGGLE_KEY (legacy)"),
        ('{"key": "abc"}', {"KAGGLE_USERNAME": "someone"}, "+ KAGGLE_USERNAME (legacy)"),
    ],
)
def test_auth_status_merges_kaggle_json_with_environment(
    kaggle_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_values: str,
    env: dict[str, str],
    expected_suffix: str,
) -> None:
    _write(kaggle_home / ".kaggle" / "kaggle.json", file_values)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    ok, details = cli._kaggle_auth_status()

    assert ok is True
    assert details.endswith(expected_suffix)


def test_auth_status_reports_incomplete_kaggle_json_without_env(kaggle_home: Path) -> None:
    _write(kaggle_home / ".kaggle" / "kaggle.json", '{"key": "abc"}')

    ok, details = cli._kaggle_auth_status()

    assert ok is False
    assert "missing username or key" in details


def test_check_kaggle_cli_does_not_block_on_missing_static_credentials(
    kaggle_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")

    assert cli.check_kaggle_cli() is None


def test_check_kaggle_cli_reports_missing_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda cmd: None)

    assert "kaggle CLI not found" in (cli.check_kaggle_cli() or "")


def test_doctor_shows_kaggle_auth_error_from_stdout(
    kaggle_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    completed_process: type[SimpleNamespace],
) -> None:
    def fake_run(cmd: list[str], *args: object, **kwargs: object) -> object:
        if cmd[:2] == ["kaggle", "--version"]:
            return completed_process(returncode=0, stdout="Kaggle CLI 2.2.4\n", stderr="")
        return completed_process(
            returncode=1,
            stdout="Authentication required to call the Kaggle API.\n\nFirst, ...\n",
            stderr="",
        )

    monkeypatch.setattr(cli.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    exit_code = cli.doctor_command(json_output=True)

    checks = {check["name"]: check for check in json.loads(capsys.readouterr().out)["checks"]}
    assert exit_code == 1
    probe = checks["kaggle auth probe"]
    assert probe["ok"] is False
    assert probe["details"].startswith("Authentication required to call the Kaggle API.")
    assert "kaggle auth login" in probe["details"]
