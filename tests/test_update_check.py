from __future__ import annotations

from pathlib import Path

import pytest
import requests

from kag.config import Config
from kag import update_check


class FakeResponse:
    def __init__(self, version: str):
        self.version = version

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, dict[str, str]]:
        return {"info": {"version": self.version}}


def test_check_for_update_returns_notice_for_newer_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(update_check.requests, "get", lambda *args, **kwargs: FakeResponse("0.2.0"))

    notice = update_check.check_for_update(
        "0.1.0",
        Config(kag_path=tmp_path),
        cache_file=tmp_path / "cache.json",
        now=1000,
    )

    assert notice is not None
    assert notice.current_version == "0.1.0"
    assert notice.latest_version == "0.2.0"
    assert "kag 0.2.0 is available" in notice.message


def test_check_for_update_returns_none_for_current_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(update_check.requests, "get", lambda *args, **kwargs: FakeResponse("0.1.0"))

    notice = update_check.check_for_update(
        "0.1.0",
        Config(kag_path=tmp_path),
        cache_file=tmp_path / "cache.json",
        now=1000,
    )

    assert notice is None


def test_check_for_update_uses_version_comparison_not_string_comparison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        update_check.requests, "get", lambda *args, **kwargs: FakeResponse("0.10.0")
    )

    notice = update_check.check_for_update(
        "0.9.0",
        Config(kag_path=tmp_path),
        cache_file=tmp_path / "cache.json",
        now=1000,
    )

    assert notice is not None
    assert notice.latest_version == "0.10.0"


def test_check_for_update_returns_none_for_failed_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed_get(*args: object, **kwargs: object) -> object:
        raise requests.Timeout("slow")

    monkeypatch.setattr(update_check.requests, "get", failed_get)

    notice = update_check.check_for_update(
        "0.1.0",
        Config(kag_path=tmp_path),
        cache_file=tmp_path / "cache.json",
        now=1000,
    )

    assert notice is None


def test_check_for_update_disabled_by_config_does_not_call_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("network should not be called")

    monkeypatch.setattr(update_check.requests, "get", fail_if_called)

    notice = update_check.check_for_update(
        "0.1.0",
        Config(kag_path=tmp_path, update_check=False),
        cache_file=tmp_path / "cache.json",
        now=1000,
    )

    assert notice is None


def test_check_for_update_disabled_by_env_does_not_call_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("network should not be called")

    monkeypatch.setenv("KAG_UPDATE_CHECK", "0")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(update_check.requests, "get", fail_if_called)

    notice = update_check.check_for_update(
        "0.1.0",
        Config.load(),
        cache_file=tmp_path / "cache.json",
        now=1000,
    )

    assert notice is None


def test_check_for_update_uses_fresh_cache_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_file = tmp_path / "cache.json"
    cache_file.write_text('{"checked_at": 900, "latest_version": "0.2.0"}')

    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("network should not be called")

    monkeypatch.setattr(update_check.requests, "get", fail_if_called)

    notice = update_check.check_for_update(
        "0.1.0",
        Config(kag_path=tmp_path),
        cache_file=cache_file,
        now=1000,
    )

    assert notice is not None
    assert notice.latest_version == "0.2.0"


def test_check_for_update_refreshes_stale_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_file = tmp_path / "cache.json"
    cache_file.write_text('{"checked_at": 1, "latest_version": "0.1.1"}')
    monkeypatch.setattr(update_check.requests, "get", lambda *args, **kwargs: FakeResponse("0.2.0"))

    notice = update_check.check_for_update(
        "0.1.0",
        Config(kag_path=tmp_path),
        cache_file=cache_file,
        now=update_check.CACHE_TTL_SECONDS + 10,
    )

    assert notice is not None
    assert notice.latest_version == "0.2.0"
    assert "0.2.0" in cache_file.read_text()


def test_check_for_update_ignores_corrupt_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_file = tmp_path / "cache.json"
    cache_file.write_text("not json")
    monkeypatch.setattr(update_check.requests, "get", lambda *args, **kwargs: FakeResponse("0.2.0"))

    notice = update_check.check_for_update(
        "0.1.0",
        Config(kag_path=tmp_path),
        cache_file=cache_file,
        now=1000,
    )

    assert notice is not None
    assert notice.latest_version == "0.2.0"


def test_upgrade_hint_detects_uv_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UV_TOOL_DIR", raising=False)

    hint = update_check.upgrade_hint("/Users/me/.local/share/uv/tools/kag/bin/python")

    assert hint == "Run: uv tool upgrade kag"


def test_upgrade_hint_detects_pipx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIPX_HOME", raising=False)

    hint = update_check.upgrade_hint("/Users/me/.local/pipx/venvs/kag/bin/python")

    assert hint == "Run: pipx upgrade kag"


def test_upgrade_hint_falls_back_for_unknown_installer() -> None:
    hint = update_check.upgrade_hint("/opt/python/bin/python")

    assert hint == "Upgrade with your Python package manager."


def test_config_load_reads_update_check_from_config_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".kag_config.toml").write_text('kag_path = "/tmp/kag"\nupdate_check = false\n')

    config = Config.load()

    assert config.update_check is False


def test_config_load_env_overrides_update_check_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("KAG_UPDATE_CHECK", "on")
    (tmp_path / ".kag_config.toml").write_text('kag_path = "/tmp/kag"\nupdate_check = false\n')

    config = Config.load()

    assert config.update_check is True


def test_config_save_writes_update_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    Config(kag_path=tmp_path / "projects", update_check=False).save()

    assert "update_check = false" in (tmp_path / ".kag_config.toml").read_text()
