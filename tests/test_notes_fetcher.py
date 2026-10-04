from __future__ import annotations

import threading

import pytest

from kag import notes_fetcher


def test_fetch_stops_between_requests_when_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    cancel = threading.Event()
    endpoints: list[str] = []

    monkeypatch.setattr(notes_fetcher, "_competition_session", lambda slug: (object(), {}))

    def fake_post(session: object, headers: dict, endpoint: str, payload: dict) -> dict:
        endpoints.append(endpoint)
        cancel.set()
        return {"id": 1, "briefDescription": "Predict survival"}

    monkeypatch.setattr(notes_fetcher, "_post_api", fake_post)

    sections, warnings = notes_fetcher.fetch_competition_markdown_sections("titanic", cancel=cancel)

    assert endpoints == ["competitions.CompetitionService/GetCompetition"]
    assert sections == {}
    assert warnings == []


def test_fetch_does_not_start_when_already_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    cancel = threading.Event()
    cancel.set()

    def fail_if_called(slug: str) -> object:
        raise AssertionError("session should not be created after cancel")

    monkeypatch.setattr(notes_fetcher, "_competition_session", fail_if_called)

    assert notes_fetcher.fetch_competition_markdown_sections("titanic", cancel=cancel) == ({}, [])
