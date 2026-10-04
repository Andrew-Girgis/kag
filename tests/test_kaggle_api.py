from __future__ import annotations

import subprocess
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from kag import kaggle_api


def _assert_fetch_error(call: Callable[[], object]) -> None:
    error_type = getattr(kaggle_api, "KaggleFetchError", Exception)
    with pytest.raises(error_type):
        call()
    assert error_type is not Exception, "Kaggle fetch failures should raise KaggleFetchError"


def test_list_competitions_page_does_not_call_real_kaggle_cli() -> None:
    with pytest.raises(AssertionError, match="real kaggle CLI"):
        kaggle_api.list_competitions_page()


def test_list_competitions_page_raises_for_missing_kaggle_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_cli(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("kaggle")

    monkeypatch.setattr(kaggle_api.subprocess, "run", missing_cli)

    _assert_fetch_error(kaggle_api.list_competitions_page)


def test_list_competitions_page_raises_for_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(cmd: list[str], *args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)

    monkeypatch.setattr(kaggle_api.subprocess, "run", timeout)

    _assert_fetch_error(kaggle_api.list_competitions_page)


def test_list_competitions_page_raises_for_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def failed_cli(*args: object, **kwargs: object) -> object:
        return completed_process(returncode=1, stdout="", stderr="Unauthorized")

    monkeypatch.setattr(kaggle_api.subprocess, "run", failed_cli)

    _assert_fetch_error(kaggle_api.list_competitions_page)


def test_list_competitions_page_raises_for_invalid_csv(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def invalid_csv(*args: object, **kwargs: object) -> object:
        return completed_process(returncode=0, stdout="title,reward\nBroken,$1\n", stderr="")

    monkeypatch.setattr(kaggle_api.subprocess, "run", invalid_csv)

    _assert_fetch_error(kaggle_api.list_competitions_page)


def test_list_competitions_page_allows_successful_empty_results(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def empty_csv(*args: object, **kwargs: object) -> object:
        return completed_process(
            returncode=0,
            stdout="ref,deadline,category,reward,teamCount,userHasEntered,userRank\n",
            stderr="",
        )

    monkeypatch.setattr(kaggle_api.subprocess, "run", empty_csv)

    competitions, has_more = kaggle_api.list_competitions_page()

    assert competitions == []
    assert has_more is False


def test_list_competitions_page_parses_real_cli_output(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def cli_output(*args: object, **kwargs: object) -> object:
        return completed_process(
            returncode=0,
            stdout=(
                "Next Page Token = abc123\n"
                "ref,deadline,category,reward,teamCount,userHasEntered,userRank\n"
                "https://www.kaggle.com/competitions/titanic,2030-01-01 00:00:00,"
                "Getting Started,Knowledge,15234,True,\n"
                "playground-series-s6e6,2026-06-30 23:59:00,Playground,Swag,3120,False,\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(kaggle_api.subprocess, "run", cli_output)

    competitions, has_more = kaggle_api.list_competitions_page(page_size=20)

    assert has_more is True
    assert [competition.slug for competition in competitions] == [
        "titanic",
        "playground-series-s6e6",
    ]
    titanic, playground = competitions
    assert titanic.team_count == "15234"
    assert titanic.is_joined is True
    assert titanic.reward == "Knowledge"
    assert titanic.deadline == "2030-01-01 00:00:00"
    assert playground.team_count == "3120"
    assert playground.is_joined is False
    assert playground.display_title == "Playground Series S6E6"


def test_list_competitions_page_stops_paging_without_next_page_token(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def last_page(*args: object, **kwargs: object) -> object:
        return completed_process(
            returncode=0,
            stdout=(
                "ref,deadline,category,reward,teamCount,userHasEntered,userRank\n"
                "titanic,2030-01-01 00:00:00,Getting Started,Knowledge,15234,False,\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(kaggle_api.subprocess, "run", last_page)

    competitions, has_more = kaggle_api.list_competitions_page(page_size=20)

    assert len(competitions) == 1
    assert has_more is False


def test_list_competitions_page_treats_no_competitions_message_as_empty(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def no_results(*args: object, **kwargs: object) -> object:
        return completed_process(returncode=0, stdout="No competitions found\n", stderr="")

    monkeypatch.setattr(kaggle_api.subprocess, "run", no_results)

    competitions, has_more = kaggle_api.list_competitions_page(search="nothing-matches")

    assert competitions == []
    assert has_more is False


def test_download_competition_returns_failure_details_for_403(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def forbidden_cli(*args: object, **kwargs: object) -> object:
        return completed_process(
            returncode=1,
            stdout="",
            stderr="403 Client Error: Forbidden for url: https://example.test\nmore details",
        )

    monkeypatch.setattr(kaggle_api.subprocess, "run", forbidden_cli)

    result = kaggle_api.download_competition("playground-series-s6e5", str(tmp_path))

    assert result.success is False
    assert "403 Client Error: Forbidden" in result.details


def test_download_competition_fails_when_no_files_are_created(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def successful_empty_cli(*args: object, **kwargs: object) -> object:
        return completed_process(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(kaggle_api.subprocess, "run", successful_empty_cli)

    result = kaggle_api.download_competition("empty-download", str(tmp_path))

    assert result.success is False
    assert "no files" in result.details.lower()


def test_download_competition_succeeds_when_files_are_created(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def successful_cli(*args: object, **kwargs: object) -> object:
        (tmp_path / "competition.zip").write_text("zip-ish")
        return completed_process(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(kaggle_api.subprocess, "run", successful_cli)

    result = kaggle_api.download_competition("successful-download", str(tmp_path))

    assert result.success is True
    assert result.files == ("competition.zip",)


def test_download_competition_reports_timeout(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(cmd: list[str], *args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=120)

    monkeypatch.setattr(kaggle_api.subprocess, "run", timeout)

    result = kaggle_api.download_competition("slow-download", str(tmp_path))

    assert result.success is False
    assert "timed out" in result.details.lower()


def test_list_competition_files_distinguishes_successful_empty_listing(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def empty_files_cli(*args: object, **kwargs: object) -> object:
        return completed_process(returncode=0, stdout="name,size,creationDate\n", stderr="")

    monkeypatch.setattr(kaggle_api.subprocess, "run", empty_files_cli)

    result = kaggle_api.list_competition_files("no-data-competition")

    assert result.success is True
    assert result.files == ()


def test_list_competition_files_rejects_zero_exit_malformed_output(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def malformed_files_cli(*args: object, **kwargs: object) -> object:
        return completed_process(returncode=0, stdout="Next Page Token = abc\n", stderr="")

    monkeypatch.setattr(kaggle_api.subprocess, "run", malformed_files_cli)

    result = kaggle_api.list_competition_files("malformed-files")

    assert result.success is False
    assert result.details == "Kaggle files response was not valid CSV"


def test_list_competition_files_includes_file_sizes(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def files_cli(cmd: list[str], *args: object, **kwargs: object) -> object:
        return completed_process(
            returncode=0,
            stdout=("name,size,creationDate\ntrain.csv,1536,2026-04-23 17:51:18.008000\n"),
            stderr="",
        )

    monkeypatch.setattr(kaggle_api.subprocess, "run", files_cli)

    result = kaggle_api.list_competition_files("sized-competition")

    assert result.success is True
    assert len(result.files) == 1
    assert result.files[0].name == "train.csv"
    assert result.files[0].size == 1536
    assert result.files[0].display_size == "1.5 KB"
    assert kaggle_api.get_competition_files("sized-competition") == ["train.csv"]


def test_list_competition_files_preserves_failure_details(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def failed_files_cli(*args: object, **kwargs: object) -> object:
        return completed_process(returncode=1, stdout="", stderr="Unauthorized\nmore")

    monkeypatch.setattr(kaggle_api.subprocess, "run", failed_files_cli)

    result = kaggle_api.list_competition_files("private-competition")

    assert result.success is False
    assert result.details == "Unauthorized"


def _files_page(names: list[str], next_token: str | None = None) -> str:
    lines = [f"Next Page Token = {next_token}"] if next_token else []
    lines.append("name,size,creationDate")
    lines.extend(f"{name},10,2026-04-23 17:51:18.008000" for name in names)
    return "\n".join(lines) + "\n"


def test_list_competition_files_follows_page_tokens(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    pages = {
        None: _files_page([f"file_{index}.csv" for index in range(200)], "page-2"),
        "page-2": _files_page([f"file_{index}.csv" for index in range(200, 400)], "page-3"),
        "page-3": _files_page(["train.csv", "test.csv"]),
    }
    commands: list[list[str]] = []

    def paged_cli(cmd: list[str], *args: object, **kwargs: object) -> object:
        commands.append(cmd)
        token = cmd[cmd.index("--page-token") + 1] if "--page-token" in cmd else None
        return completed_process(returncode=0, stdout=pages[token], stderr="")

    monkeypatch.setattr(kaggle_api.subprocess, "run", paged_cli)

    result = kaggle_api.list_competition_files("many-files")

    assert result.success is True
    assert len(result.files) == 402
    assert result.files[-2].name == "train.csv"
    assert len(commands) == 3
    assert all(cmd[cmd.index("--page-size") + 1] == "200" for cmd in commands)
    assert "--page-token" not in commands[0]
    assert commands[1][commands[1].index("--page-token") + 1] == "page-2"


def test_list_competition_files_stops_on_repeated_page_token(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    calls: list[list[str]] = []

    def looping_cli(cmd: list[str], *args: object, **kwargs: object) -> object:
        calls.append(cmd)
        return completed_process(returncode=0, stdout=_files_page(["a.csv"], "same"), stderr="")

    monkeypatch.setattr(kaggle_api.subprocess, "run", looping_cli)

    result = kaggle_api.list_competition_files("looping")

    assert result.success is True
    assert len(calls) == 2
    assert [file.name for file in result.files] == ["a.csv", "a.csv"]


def test_list_competition_files_reports_failure_on_later_page(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def failing_second_page(cmd: list[str], *args: object, **kwargs: object) -> object:
        if "--page-token" in cmd:
            return completed_process(returncode=1, stdout="", stderr="Rate limited")
        return completed_process(returncode=0, stdout=_files_page(["a.csv"], "next"), stderr="")

    monkeypatch.setattr(kaggle_api.subprocess, "run", failing_second_page)

    result = kaggle_api.list_competition_files("flaky")

    assert result.success is False
    assert result.details == "Rate limited"


def test_list_competition_files_ignores_token_text_in_data_rows(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    calls: list[list[str]] = []

    def last_page(cmd: list[str], *args: object, **kwargs: object) -> object:
        calls.append(cmd)
        return completed_process(
            returncode=0,
            stdout=_files_page(["train.csv", "Next Page Token = odd-name.csv"]),
            stderr="",
        )

    monkeypatch.setattr(kaggle_api.subprocess, "run", last_page)

    result = kaggle_api.list_competition_files("odd-names")

    assert result.success is True
    assert result.truncated is False
    assert len(calls) == 1
    assert [file.name for file in result.files] == ["train.csv", "Next Page Token = odd-name.csv"]


def test_list_competition_files_flags_truncation_at_page_cap(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    calls: list[list[str]] = []

    def endless_pages(cmd: list[str], *args: object, **kwargs: object) -> object:
        calls.append(cmd)
        return completed_process(
            returncode=0,
            stdout=_files_page([f"file_{len(calls)}.csv"], f"token-{len(calls)}"),
            stderr="",
        )

    monkeypatch.setattr(kaggle_api.subprocess, "run", endless_pages)

    result = kaggle_api.list_competition_files("endless")

    assert len(calls) == kaggle_api.MAX_FILE_LIST_PAGES
    assert result.success is True
    assert result.truncated is True
    assert len(result.files) == kaggle_api.MAX_FILE_LIST_PAGES
    assert "stopped after" in result.details


def test_list_competitions_page_ignores_token_text_after_header(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def cli_output(*args: object, **kwargs: object) -> object:
        return completed_process(
            returncode=0,
            stdout=(
                "ref,deadline,category,reward,teamCount,userHasEntered,userRank\n"
                "titanic,2030-01-01 00:00:00,Getting Started,Next Page Token = x,1,False,\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(kaggle_api.subprocess, "run", cli_output)

    competitions, has_more = kaggle_api.list_competitions_page(page_size=20)

    assert len(competitions) == 1
    assert has_more is False
