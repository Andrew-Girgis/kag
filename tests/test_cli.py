from __future__ import annotations

import json
import sys
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
    assert "kag login" in details


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


def test_check_kaggle_cli_reports_missing_bundled_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "bundled_kaggle_available", lambda: False)

    assert "reinstall kag" in (cli.check_kaggle_cli() or "")


def test_check_kaggle_cli_does_not_need_kaggle_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda cmd: None)

    assert cli.check_kaggle_cli() is None


def test_kaggle_commands_use_the_bundled_cli() -> None:
    assert cli.kaggle_command("auth", "login") == [
        sys.executable,
        "-P",
        "-m",
        "kaggle",
        "auth",
        "login",
    ]


def test_doctor_shows_kaggle_auth_error_from_stdout(
    kaggle_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    completed_process: type[SimpleNamespace],
) -> None:
    def fake_run(cmd: list[str], *args: object, **kwargs: object) -> object:
        if cmd[1:] == ["-P", "-m", "kaggle", "--version"]:
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
    assert "kag login" in probe["details"]


def test_doctor_reports_bundled_cli(
    kaggle_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    completed_process: type[SimpleNamespace],
) -> None:
    def fake_run(cmd: list[str], *args: object, **kwargs: object) -> object:
        if cmd[1:] == ["-P", "-m", "kaggle", "--version"]:
            return completed_process(returncode=0, stdout="Kaggle CLI 2.2.4\n", stderr="")
        return completed_process(returncode=0, stdout="ref,deadline\n", stderr="")

    monkeypatch.setattr(cli.shutil, "which", lambda cmd: None)
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    cli.doctor_command(json_output=True)

    checks = {check["name"]: check for check in json.loads(capsys.readouterr().out)["checks"]}
    assert checks["kaggle CLI"] == {
        "name": "kaggle CLI",
        "ok": True,
        "details": "bundled with kag (Kaggle CLI 2.2.4)",
    }
    assert checks["kaggle auth probe"]["ok"] is True


def test_login_runs_bundled_auth_login_then_verifies(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    completed_process: type[SimpleNamespace],
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *args: object, **kwargs: object) -> object:
        calls.append(cmd)
        logged_in = any("login" in call for call in calls)
        if "login" in cmd or logged_in:
            return completed_process(returncode=0, stdout="ref,deadline\n", stderr="")
        return completed_process(returncode=1, stdout="Authentication required", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli.sys, "argv", ["kag", "login"])

    cli.main()

    assert calls[0][1:6] == ["-P", "-m", "kaggle", "competitions", "list"]
    assert calls[1] == [sys.executable, "-P", "-m", "kaggle", "auth", "login"]
    assert calls[2][1:6] == ["-P", "-m", "kaggle", "competitions", "list"]
    assert "Logged in. kag can reach Kaggle." in capsys.readouterr().out


def test_login_when_already_logged_in_does_nothing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    completed_process: type[SimpleNamespace],
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *args: object, **kwargs: object) -> object:
        calls.append(cmd)
        return completed_process(returncode=0, stdout="ref,deadline\n", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert cli.login_command([]) == 0
    assert not any("login" in call for call in calls)
    assert "Already logged in" in capsys.readouterr().out


def test_login_force_runs_login_and_accepts_existing_session(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *args: object, **kwargs: object) -> object:
        calls.append(cmd)
        if "login" in cmd:
            return completed_process(returncode=1, stdout="", stderr="Already logged in")
        return completed_process(returncode=0, stdout="ref,deadline\n", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert cli.login_command(["--force"]) == 0
    assert calls[0] == [sys.executable, "-P", "-m", "kaggle", "auth", "login", "--force"]


def test_login_reports_cancelled_login(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    completed_process: type[SimpleNamespace],
) -> None:
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda cmd, *args, **kwargs: completed_process(returncode=2, stdout="", stderr=""),
    )

    assert cli.login_command([]) == 2
    assert "did not complete" in capsys.readouterr().err


def test_login_reports_rejected_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    completed_process: type[SimpleNamespace],
) -> None:
    def fake_run(cmd: list[str], *args: object, **kwargs: object) -> object:
        if "login" in cmd:
            return completed_process(returncode=0, stdout="", stderr="")
        return completed_process(returncode=1, stdout="401 - Unauthorized", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert cli.login_command([]) == 1
    assert "401 - Unauthorized" in capsys.readouterr().err


def test_login_help_does_not_run_kaggle(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("help should not run kaggle")

    monkeypatch.setattr(cli.subprocess, "run", fail_if_called)

    assert cli.login_command(["--help"]) == 0
    assert capsys.readouterr().out == cli.LOGIN_HELP_TEXT + "\n"


def test_kaggle_passthrough_runs_bundled_cli_with_arguments(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *args: object, **kwargs: object) -> object:
        calls.append(cmd)
        return completed_process(returncode=7, stdout="", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(
        cli.sys, "argv", ["kag", "kaggle", "competitions", "submit", "-c", "titanic", "--help"]
    )

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 7
    assert calls == [
        [sys.executable, "-P", "-m", "kaggle", "competitions", "submit", "-c", "titanic", "--help"]
    ]


def test_bundled_cli_ignores_modules_in_the_working_directory() -> None:
    command = cli.kaggle_command("--version")

    assert command[:4] == [sys.executable, "-P", "-m", "kaggle"]


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[object]]:
    calls: dict[str, list[object]] = {"tui": [], "doctor": []}
    monkeypatch.setattr(cli, "run_tui", lambda query: calls["tui"].append(query) or 0)
    monkeypatch.setattr(
        cli, "doctor_command", lambda json_output=False: calls["doctor"].append(json_output) or 0
    )
    return calls


@pytest.mark.parametrize(
    ("argv", "query"),
    [
        ([], ""),
        (["titanic"], "titanic"),
        (["house", "prices"], "house prices"),
        (["search", "new"], "new"),
        (["search", "login"], "login"),
        (["search"], ""),
    ],
)
def test_search_and_bare_queries_open_the_picker(
    recorded: dict[str, list[object]], argv: list[str], query: str
) -> None:
    assert cli.run_command(argv) == 0
    assert recorded["tui"] == [query]


@pytest.mark.parametrize(
    ("argv", "json_output"),
    [
        (["doctor"], False),
        (["doctor", "--json"], True),
        (["--doctor"], False),
        (["--doctor", "--json"], True),
    ],
)
def test_doctor_command_and_alias(
    recorded: dict[str, list[object]], argv: list[str], json_output: bool
) -> None:
    assert cli.run_command(argv) == 0
    assert recorded["doctor"] == [json_output]
    assert recorded["tui"] == []


@pytest.mark.parametrize("argv", [["init"], ["--init"]])
def test_init_command_and_alias(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.run_command(argv) == 0
    assert capsys.readouterr().out.startswith("kag() {")


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--bogus"], "unknown option: --bogus"),
        (["titanic", "--json"], "unknown option: --json"),
        (["doctor", "--verbose"], "unknown doctor option: --verbose"),
        (["init", "extra"], "init takes no arguments: extra"),
    ],
)
def test_unknown_options_are_usage_errors(
    recorded: dict[str, list[object]],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    message: str,
) -> None:
    assert cli.run_command(argv) == 2
    assert f"kag: {message}" in capsys.readouterr().err
    assert recorded["tui"] == []
    assert recorded["doctor"] == []


@pytest.mark.parametrize(
    ("argv", "text"),
    [
        (["doctor", "--help"], "DOCTOR_HELP_TEXT"),
        (["search", "-h"], "SEARCH_HELP_TEXT"),
        (["init", "--help"], "INIT_HELP_TEXT"),
        (["--help"], "HELP_TEXT"),
    ],
)
def test_command_help(
    recorded: dict[str, list[object]],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    text: str,
) -> None:
    assert cli.run_command(argv) == 0
    assert capsys.readouterr().out == getattr(cli, text) + "\n"
    assert recorded["tui"] == []


def test_help_lists_every_command() -> None:
    for command in cli.COMMANDS:
        assert f"kag {command}" in cli.HELP_TEXT
    assert "--doctor" not in cli.HELP_TEXT
    assert "--init" not in cli.HELP_TEXT
