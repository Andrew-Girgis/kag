from __future__ import annotations

import subprocess
from collections.abc import Sequence
from types import SimpleNamespace

import pytest
import requests


def _is_kaggle_command(cmd: Sequence[str] | str) -> bool:
    if isinstance(cmd, str):
        return cmd.startswith("kaggle ")
    return bool(cmd) and cmd[0] == "kaggle"


@pytest.fixture(autouse=True)
def block_real_kaggle_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    real_run = subprocess.run
    real_popen = subprocess.Popen

    def guarded_run(cmd: Sequence[str] | str, *args: object, **kwargs: object) -> object:
        if _is_kaggle_command(cmd):
            raise AssertionError("tests must not call the real kaggle CLI")
        return real_run(cmd, *args, **kwargs)

    def guarded_popen(cmd: Sequence[str] | str, *args: object, **kwargs: object) -> object:
        if _is_kaggle_command(cmd):
            raise AssertionError("tests must not call the real kaggle CLI")
        return real_popen(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded_run)
    monkeypatch.setattr(subprocess, "Popen", guarded_popen)


@pytest.fixture(autouse=True)
def block_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_request(*args: object, **kwargs: object) -> object:
        raise AssertionError("tests must not make real HTTP requests")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked_request)


@pytest.fixture
def completed_process() -> type[SimpleNamespace]:
    return SimpleNamespace
