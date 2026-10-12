from __future__ import annotations

from pathlib import Path

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


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(config.Path, "home", classmethod(lambda cls: tmp_path))
    for name in ("KAG_PATH", "KAG_THEME", "KAG_UPDATE_CHECK"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_defaults_apply_without_config_or_environment(home: Path) -> None:
    loaded = Config.load()

    assert loaded.kag_path == config.KAG_PATH_DEFAULT
    assert loaded.default_editor is None
    assert loaded.auto_venv is True
    assert loaded.auto_git is True
    assert loaded.update_check is True


def test_config_file_overrides_defaults(home: Path) -> None:
    (home / ".kag_config.toml").write_text(
        'kag_path = "/data/kaggle"\ndefault_editor = "code"\n'
        "auto_venv = false\nauto_git = false\nupdate_check = false\n"
    )

    loaded = Config.load()

    assert loaded.kag_path == Path("/data/kaggle")
    assert loaded.default_editor == "code"
    assert loaded.auto_venv is False
    assert loaded.auto_git is False
    assert loaded.update_check is False


def test_environment_overrides_config_file(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (home / ".kag_config.toml").write_text(
        'kag_path = "/data/kaggle"\nupdate_check = true\ntheme = "nord"\n'
    )
    monkeypatch.setenv("KAG_PATH", "/scratch/kaggle")
    monkeypatch.setenv("KAG_UPDATE_CHECK", "0")
    monkeypatch.setenv("KAG_THEME", "kag")

    loaded = Config.load()

    assert loaded.kag_path == Path("/scratch/kaggle")
    assert loaded.update_check is False
    assert loaded.theme == "kag"


def test_empty_kag_path_environment_is_ignored(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (home / ".kag_config.toml").write_text('kag_path = "/data/kaggle"\n')
    monkeypatch.setenv("KAG_PATH", "  ")

    assert Config.load().kag_path == Path("/data/kaggle")


def test_invalid_config_falls_back_to_defaults_but_keeps_environment(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (home / ".kag_config.toml").write_text('kag_path = "/data/kaggle"\nauto_git = \n')
    monkeypatch.setenv("KAG_PATH", "/scratch/kaggle")

    loaded = Config.load()

    assert loaded.kag_path == Path("/scratch/kaggle")
    assert loaded.auto_git is True


def test_kag_path_environment_is_used_exactly(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAG_PATH", "/data/Kaggle ")

    assert Config.load().kag_path == Path("/data/Kaggle ")


def test_kag_path_expands_home_and_variables(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DATA_ROOT", "/data")
    (home / ".kag_config.toml").write_text('kag_path = "~/Kaggle"\n')

    assert Config.load().kag_path == home / "Kaggle"

    monkeypatch.setenv("KAG_PATH", "$DATA_ROOT/kaggle")
    assert Config.load().kag_path == Path("/data/kaggle")


def test_invalid_config_is_reported_instead_of_silently_ignored(home: Path) -> None:
    (home / ".kag_config.toml").write_text("auto_git = \n")

    loaded = Config.load()

    assert len(loaded.warnings) == 1
    assert ".kag_config.toml" in loaded.warnings[0] and "defaults" in loaded.warnings[0]


def test_valid_config_has_no_warnings(home: Path) -> None:
    (home / ".kag_config.toml").write_text("auto_git = false\n")

    assert Config.load().warnings == []


def test_find_editor_matches_key_or_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _installed(monkeypatch, "code", "jupyter-lab")
    loaded = Config(kag_path=tmp_path)

    assert loaded.find_editor("jupyter")["cmd"] == "jupyter-lab"
    assert loaded.find_editor("jupyter-lab")["key"] == "jupyter"
    assert loaded.find_editor("cursor") is None
    assert loaded.find_editor(None) is None


def test_unresolvable_home_in_kag_path_is_reported_not_raised(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (home / ".kag_config.toml").write_text('kag_path = "~nobody-kag-test/a"\nauto_git = false\n')

    loaded = Config.load()
    assert loaded.kag_path == config.KAG_PATH_DEFAULT
    assert loaded.auto_git is False
    assert len(loaded.warnings) == 1 and "kag_path" in loaded.warnings[0]

    monkeypatch.setenv("KAG_PATH", "~nobody-kag-test/b")
    loaded = Config.load()
    assert loaded.kag_path == config.KAG_PATH_DEFAULT
    assert any("KAG_PATH" in warning for warning in loaded.warnings)
