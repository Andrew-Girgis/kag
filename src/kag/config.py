import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

KAG_PATH_DEFAULT = Path.home() / "Kaggle"

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
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)

    def available_editors(self) -> list[dict]:
        editors = []
        for _key, info in KNOWN_EDITORS.items():
            if shutil.which(info["cmd"]):
                editors.append({**info, "key": _key})
        return editors

    @classmethod
    def load(cls) -> "Config":
        config_path = Path.home() / ".kag_config.toml"
        kag_path = Path(os.environ.get("KAG_PATH", str(KAG_PATH_DEFAULT)))
        update_check = True

        if config_path.exists():
            try:
                import tomllib

                with open(config_path, "rb") as f:
                    data = tomllib.load(f)
                kag_path = Path(data.get("kag_path", str(kag_path)))
                default_editor = data.get("default_editor")
                auto_venv = data.get("auto_venv", True)
                section = data.get("environment")
                if isinstance(section, dict) and isinstance(section.get("create"), bool):
                    auto_venv = section["create"]
                auto_git = data.get("auto_git", True)
                update_check = data.get("update_check", update_check)
                update_check = _env_update_check(update_check)
                return cls(
                    kag_path=kag_path,
                    default_editor=default_editor,
                    auto_venv=auto_venv,
                    auto_git=auto_git,
                    update_check=update_check,
                    environment=EnvironmentConfig.from_toml(section),
                )
            except Exception:
                pass

        return cls(kag_path=kag_path, update_check=_env_update_check(update_check))

    def save(self) -> None:
        config_path = Path.home() / ".kag_config.toml"
        lines = [
            f'kag_path = "{self.kag_path}"',
            f'default_editor = "{self.default_editor or ""}"',
            f"auto_venv = {str(self.auto_venv).lower()}",
            f"auto_git = {str(self.auto_git).lower()}",
            f"update_check = {str(self.update_check).lower()}",
        ]
        config_path.write_text("\n".join(lines) + "\n")


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
