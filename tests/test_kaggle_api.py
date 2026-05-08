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
