from __future__ import annotations

import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from kag import kaggle_sdk


def _is_kaggle_command(cmd: Sequence[str] | str) -> bool:
    if isinstance(cmd, str):
        return cmd.startswith("kaggle ") or " -m kaggle" in cmd
    parts = list(cmd)
    if not parts:
        return False
    return Path(str(parts[0])).name == "kaggle" or parts[1:3] == ["-m", "kaggle"]


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
def block_real_kaggle_sdk(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def blocked_load_api() -> object:
        raise kaggle_sdk.KaggleSdkError("tests must not call the real Kaggle API")

    kaggle_sdk.reset()
    monkeypatch.setattr(kaggle_sdk, "_load_api", blocked_load_api)
    yield
    kaggle_sdk.reset()


@pytest.fixture(autouse=True)
def block_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_request(*args: object, **kwargs: object) -> object:
        raise AssertionError("tests must not make real HTTP requests")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked_request)


@pytest.fixture
def completed_process() -> type[SimpleNamespace]:
    return SimpleNamespace
