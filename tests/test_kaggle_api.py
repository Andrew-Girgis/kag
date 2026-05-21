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
            stdout="ref,title,deadline,reward,teamsCount\n",
            stderr="",
        )

    monkeypatch.setattr(kaggle_api.subprocess, "run", empty_csv)

    competitions, has_more = kaggle_api.list_competitions_page()

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


def test_list_competition_files_includes_file_sizes(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    def files_cli(*args: object, **kwargs: object) -> object:
        return completed_process(
            returncode=0,
            stdout=(
                "Next Page Token = abc\n"
                "name,size,creationDate\n"
                "train.csv,1536,2026-04-23 17:51:18.008000\n"
            ),
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
