from __future__ import annotations

import pytest

from kag import config
from kag.config import Config


def _installed(monkeypatch: pytest.MonkeyPatch, *commands: str) -> None:
    monkeypatch.setattr(
        config.shutil,
        "which",
        lambda cmd: f"/usr/local/bin/{cmd}" if cmd in commands else None,
    )


def test_jupyter_lab_detected_from_jupyter_lab_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _installed(monkeypatch, "jupyter-lab")

    editors = Config().available_editors()

    assert editors == [{"cmd": "jupyter-lab", "name": "Jupyter Lab", "key": "jupyter"}]


def test_jupyter_lab_not_offered_for_classic_jupyter_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _installed(monkeypatch, "jupyter", "code")

    editors = Config().available_editors()

    assert [editor["cmd"] for editor in editors] == ["code"]
