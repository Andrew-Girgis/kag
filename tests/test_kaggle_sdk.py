from __future__ import annotations

import contextlib
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from kag import kaggle_api, kaggle_sdk, project
from kag.config import Config
from kag.kaggle_api import Competition


def _competition_item(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "ref": "https://www.kaggle.com/competitions/titanic",
        "title": "Titanic - Machine Learning from Disaster",
        "description": "Start here! Predict survival on the Titanic",
        "category": "Getting Started",
        "reward": "Knowledge",
        "deadline": "2030-01-01 00:00:00",
        "new_entrant_deadline": None,
        "merger_deadline": None,
        "team_count": 10648,
        "user_has_entered": True,
        "evaluation_metric": "Categorization Accuracy",
        "max_daily_submissions": 10,
        "max_team_size": 10,
        "is_kernels_submissions_only": False,
        "submissions_disabled": False,
        "url": "https://www.kaggle.com/competitions/titanic",
        "tags": [SimpleNamespace(name="binary classification"), SimpleNamespace(name="tabular")],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeApi:
    def __init__(self, competitions: list[SimpleNamespace], token: str = "") -> None:
        self.competitions = competitions
        self.token = token
        self.list_calls: list[dict[str, object]] = []

    def competitions_list(self, **kwargs: object) -> SimpleNamespace:
        self.list_calls.append(kwargs)
        print("noise from the kaggle library")
        return SimpleNamespace(competitions=self.competitions, next_page_token=self.token)

    @contextlib.contextmanager
    def build_kaggle_client(self) -> Iterator[SimpleNamespace]:
        client = SimpleNamespace(get_competition=lambda request: self.competitions[0])
        yield SimpleNamespace(competitions=SimpleNamespace(competition_api_client=client))


def _use_api(monkeypatch: pytest.MonkeyPatch, api: object) -> None:
    kaggle_sdk.reset()
    monkeypatch.setattr(kaggle_sdk, "_load_api", lambda: api)


def test_list_competitions_maps_fields_and_silences_library_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = FakeApi([_competition_item(), _competition_item(ref="playground-series-s6e1")])
    _use_api(monkeypatch, api)

    listed, has_more = kaggle_sdk.list_competitions(group="entered", page=2, page_size=20)

    assert [item.slug for item in listed] == ["titanic", "playground-series-s6e1"]
    first = listed[0]
    assert first.title == "Titanic - Machine Learning from Disaster"
    assert first.team_count == 10648
    assert first.user_has_entered is True
    assert has_more is False
    assert api.list_calls == [{"group": "entered", "page": 2, "page_size": 20, "search": None}]
    assert capsys.readouterr().out == ""


def test_list_competitions_reports_more_pages_from_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_api(monkeypatch, FakeApi([_competition_item()], token="next"))

    _, has_more = kaggle_sdk.list_competitions(page_size=20)

    assert has_more is True


def test_get_competition_details_maps_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_api(monkeypatch, FakeApi([_competition_item()]))

    details = kaggle_sdk.get_competition_details("titanic")

    assert details.title == "Titanic - Machine Learning from Disaster"
    assert details.evaluation_metric == "Categorization Accuracy"
    assert details.max_daily_submissions == 10
    assert details.new_entrant_deadline == ""
    assert details.tags == ("binary classification", "tabular")
    assert details.is_kernels_submissions_only is False


def test_library_exit_during_login_becomes_sdk_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def exiting_login() -> object:
        print("Authentication required to call the Kaggle API.")
        raise SystemExit(1)

    kaggle_sdk.reset()
    monkeypatch.setattr(kaggle_sdk, "_load_api", exiting_login)

    with pytest.raises(kaggle_sdk.KaggleSdkError):
        kaggle_sdk.list_competitions()
    assert capsys.readouterr().out == ""


def test_library_call_failure_becomes_sdk_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenApi:
        def competitions_list(self, **kwargs: object) -> object:
            raise ValueError("Invalid group specified")

    _use_api(monkeypatch, BrokenApi())

    with pytest.raises(kaggle_sdk.KaggleSdkError, match="Invalid group"):
        kaggle_sdk.list_competitions(group="nope")


def test_competition_list_uses_library_titles(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_api(monkeypatch, FakeApi([_competition_item()]))

    competitions, _ = kaggle_api.list_competitions_page(group="general")

    assert competitions[0].title == "Titanic - Machine Learning from Disaster"
    assert competitions[0].team_count == "10648"
    assert competitions[0].is_joined is True


def test_competition_list_falls_back_to_cli_when_library_fails(
    monkeypatch: pytest.MonkeyPatch,
    completed_process: type[SimpleNamespace],
) -> None:
    monkeypatch.setattr(
        kaggle_api.subprocess,
        "run",
        lambda *args, **kwargs: completed_process(
            returncode=0,
            stdout=(
                "ref,deadline,category,reward,teamCount,userHasEntered,userRank\n"
                "titanic,2030-01-01 00:00:00,Getting Started,Knowledge,1,False,\n"
            ),
            stderr="",
        ),
    )

    competitions, _ = kaggle_api.list_competitions_page(group="general")

    assert [competition.slug for competition in competitions] == ["titanic"]
    assert competitions[0].title == "titanic"


def test_notes_include_competition_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_api(monkeypatch, FakeApi([_competition_item(max_team_size=5)]))
    monkeypatch.setattr(project, "get_competition_files", lambda slug: ["train.csv"])
    monkeypatch.setattr(
        project, "fetch_competition_markdown_sections", lambda slug, **kwargs: ({}, [])
    )

    project_path = project.create_project(
        Competition(slug="titanic", title="titanic", deadline="", reward="", team_count="0"),
        Config(kag_path=tmp_path, auto_git=False, auto_venv=False),
        download_files=False,
    )

    notes = (Path(project_path) / "notes.md").read_text()
    assert notes.startswith("# Titanic - Machine Learning from Disaster\n\nStart here!")
    assert "**Evaluation metric:** Categorization Accuracy" in notes
    assert "**Max daily submissions:** 10" in notes
    assert "**Max team size:** 5" in notes
    assert "**Teams:** 10648" in notes
    assert "Join deadline" not in notes


def test_concurrent_calls_do_not_overlap_or_leak_stream_redirection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = 0
    max_active = 0
    counter_lock = threading.Lock()

    class SlowApi:
        def competitions_list(self, **kwargs: object) -> SimpleNamespace:
            nonlocal active, max_active
            with counter_lock:
                active += 1
                max_active = max(max_active, active)
            print("library noise")
            time.sleep(0.05)
            with counter_lock:
                active -= 1
            return SimpleNamespace(competitions=[], next_page_token="")

    _use_api(monkeypatch, SlowApi())
    original_stdout, original_stderr = sys.stdout, sys.stderr
    threads = [threading.Thread(target=kaggle_sdk.list_competitions) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1
    assert sys.stdout is original_stdout
    assert sys.stderr is original_stderr
