from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from packaging.version import InvalidVersion, Version

from .config import Config

PYPI_URL = "https://pypi.org/pypi/kag/json"
CACHE_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class UpdateNotice:
    current_version: str
    latest_version: str
    upgrade_hint: str

    @property
    def message(self) -> str:
        return (
            f"kag {self.latest_version} is available. "
            f"You have {self.current_version}. {self.upgrade_hint}"
        )


def cache_path() -> Path:
    cache_home = os.environ.get("XDG_CACHE_HOME")
    if cache_home:
        return Path(cache_home) / "kag" / "update_check.json"
    return Path.home() / ".cache" / "kag" / "update_check.json"


def check_for_update(
    current_version: str,
    config: Config,
    cache_file: Path | None = None,
    now: float | None = None,
) -> UpdateNotice | None:
    if not config.update_check:
        return None

    current_time = time.time() if now is None else now
    cache_file = cache_path() if cache_file is None else cache_file
    latest_version = _read_cached_latest_version(cache_file, current_time)

    if latest_version is None:
        latest_version = _fetch_latest_version()
        if latest_version is None:
            return None
        _write_cache(cache_file, latest_version, current_time)

    if not _is_newer(latest_version, current_version):
        return None

    return UpdateNotice(
        current_version=current_version,
        latest_version=latest_version,
        upgrade_hint=upgrade_hint(),
    )


def upgrade_hint(executable: str | None = None) -> str:
    executable = sys.executable if executable is None else executable
    normalized = executable.replace("\\", "/").lower()

    uv_tool_dir = os.environ.get("UV_TOOL_DIR")
    if uv_tool_dir and normalized.startswith(uv_tool_dir.replace("\\", "/").lower()):
        return "Run: uv tool upgrade kag"
    if "/uv/tools/" in normalized or "/uv/tool/" in normalized:
        return "Run: uv tool upgrade kag"

    pipx_home = os.environ.get("PIPX_HOME")
    if pipx_home and normalized.startswith(pipx_home.replace("\\", "/").lower()):
        return "Run: pipx upgrade kag"
    if "/pipx/venvs/kag/" in normalized or "/.local/pipx/venvs/kag/" in normalized:
        return "Run: pipx upgrade kag"

    return "Upgrade with your Python package manager."


def _fetch_latest_version() -> str | None:
    try:
        response = requests.get(PYPI_URL, timeout=2)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None

    version = payload.get("info", {}).get("version")
    return version if isinstance(version, str) and version else None


def _read_cached_latest_version(cache_file: Path, now: float) -> str | None:
    try:
        payload = json.loads(cache_file.read_text())
        checked_at = float(payload.get("checked_at", 0))
        latest_version = payload.get("latest_version")
    except Exception:
        return None

    if now - checked_at > CACHE_TTL_SECONDS:
        return None
    if not isinstance(latest_version, str) or not latest_version:
        return None
    return latest_version


def _write_cache(cache_file: Path, latest_version: str, now: float) -> None:
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"checked_at": now, "latest_version": latest_version}))
    except Exception:
        pass


def _is_newer(latest_version: str, current_version: str) -> bool:
    try:
        return Version(latest_version) > Version(current_version)
    except InvalidVersion:
        return False
