import os
import re
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

KAG_PATH_DEFAULT = Path.home() / "Kaggle"
DEFAULT_THEME = "terminal"
THEME_ENV = "KAG_THEME"

FALSE_VALUES = {"0", "false", "no", "off"}
TRUE_VALUES = {"1", "true", "yes", "on"}

DEFAULT_PACKAGES = ("pandas", "numpy", "matplotlib", "seaborn", "scikit-learn", "ipykernel")
INSTALL_MODES = ("ask", "always", "never")

KNOWN_EDITORS = {
    "code": {"cmd": "code", "name": "VS Code"},
    "cursor": {"cmd": "cursor", "name": "Cursor"},
    "zed": {"cmd": "zed", "name": "Zed"},
    "windsurf": {"cmd": "windsurf", "name": "Windsurf"},
    "jupyter": {"cmd": "jupyter-lab", "name": "Jupyter Lab"},
}


@dataclass
class EnvironmentConfig:
    install: str = "ask"
    python: str = ""
    packages: list[str] = field(default_factory=lambda: list(DEFAULT_PACKAGES))
    command: list[str] = field(default_factory=list)

    @classmethod
    def from_toml(cls, section: object) -> "EnvironmentConfig":
        if not isinstance(section, dict):
            return cls()
        default = cls()
        install = section.get("install", default.install)
        python = section.get("python", default.python)
        packages = section.get("packages", default.packages)
        command = section.get("command", default.command)
        return cls(
            install=install if install in INSTALL_MODES else default.install,
            python=python.strip() if isinstance(python, str) else default.python,
            packages=packages if _is_string_list(packages) else default.packages,
            command=command if _is_string_list(command) else default.command,
        )


@dataclass
class Config:
    kag_path: Path = KAG_PATH_DEFAULT
    default_editor: str | None = None
    auto_venv: bool = True
    auto_git: bool = True
    update_check: bool = True
    theme: str = DEFAULT_THEME
    theme_source: str = "default"
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    warnings: list[str] = field(default_factory=list)

    def available_editors(self) -> list[dict]:
        editors = []
        for _key, info in KNOWN_EDITORS.items():
            if shutil.which(info["cmd"]):
                editors.append({**info, "key": _key})
        return editors

    def find_editor(self, name: str | None) -> dict | None:
        if not name:
            return None
        for editor in self.available_editors():
            if name in (editor["key"], editor["cmd"]):
                return editor
        return None

    @classmethod
    def load(cls) -> "Config":
        path = config_path()
        kag_path = KAG_PATH_DEFAULT
        update_check = True
        warnings: list[str] = []

        if path.exists():
            try:
                with open(path, "rb") as f:
                    data = tomllib.load(f)
                kag_path = (
                    _expand_path(data.get("kag_path", str(kag_path)), "kag_path", warnings)
                    or KAG_PATH_DEFAULT
                )
                default_editor = data.get("default_editor")
                auto_venv = data.get("auto_venv", True)
                section = data.get("environment")
                if isinstance(section, dict) and isinstance(section.get("create"), bool):
                    auto_venv = section["create"]
                auto_git = data.get("auto_git", True)
                update_check = data.get("update_check", update_check)
                update_check = _env_update_check(update_check)
                config = cls(
                    kag_path=kag_path,
                    default_editor=default_editor,
                    auto_venv=auto_venv,
                    auto_git=auto_git,
                    update_check=update_check,
                    environment=EnvironmentConfig.from_toml(section),
                    warnings=warnings,
                )
                theme = data.get("theme")
                if isinstance(theme, str) and theme.strip():
                    config.theme, config.theme_source = theme, "config"
                return _env_overrides(config)
            except Exception as exc:
                warnings.append(f"Couldn't read {path} ({exc}); using the defaults instead.")

        return _env_overrides(
            cls(
                kag_path=KAG_PATH_DEFAULT,
                update_check=_env_update_check(True),
                warnings=warnings,
            )
        )


def _env_overrides(config: Config) -> Config:
    kag_path = os.environ.get("KAG_PATH", "")
    if kag_path.strip():
        config.kag_path = _expand_path(kag_path, "KAG_PATH", config.warnings) or config.kag_path
    theme = os.environ.get(THEME_ENV, "").strip()
    if theme:
        config.theme, config.theme_source = theme, THEME_ENV
    return config


def _expand_path(value: str, source: str, warnings: list[str]) -> Path | None:
    try:
        return Path(os.path.expandvars(value)).expanduser()
    except RuntimeError as exc:
        warnings.append(f"Couldn't expand {source} {value!r} ({exc}); ignoring it.")
        return None


def config_path() -> Path:
    return Path.home() / ".kag_config.toml"


def save_theme(name: str, path: Path | None = None) -> Path:
    path = path or config_path()
    text = path.read_text() if path.exists() else ""
    lines = text.splitlines()
    first_table = next(
        (index for index, line in enumerate(lines) if line.lstrip().startswith("[")),
        len(lines),
    )
    entry = f'theme = "{name}"'
    for index in range(first_table):
        if re.match(r"\s*theme\s*=", lines[index]):
            lines[index] = entry
            break
    else:
        lines[first_table:first_table] = [entry, ""] if first_table < len(lines) else [entry]
    updated = "\n".join(lines) + "\n"
    tomllib.loads(updated)
    path.write_text(updated)
    return path


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _env_update_check(default: bool) -> bool:
    value = os.environ.get("KAG_UPDATE_CHECK")
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in FALSE_VALUES:
        return False
    if normalized in TRUE_VALUES:
        return True
    return default
