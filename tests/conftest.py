from __future__ import annotations

import subprocess
from collections.abc import Sequence
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def block_real_kaggle_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    real_run = subprocess.run

    def guarded_run(cmd: Sequence[str] | str, *args: object, **kwargs: object) -> object:
        if isinstance(cmd, Sequence) and not isinstance(cmd, str) and cmd and cmd[0] == "kaggle":
            raise AssertionError("tests must not call the real kaggle CLI")
        if isinstance(cmd, str) and cmd.startswith("kaggle "):
            raise AssertionError("tests must not call the real kaggle CLI")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded_run)


@pytest.fixture
def completed_process() -> type[SimpleNamespace]:
    return SimpleNamespace
