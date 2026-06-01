import os
import shutil
from dataclasses import dataclass
from pathlib import Path

KAG_PATH_DEFAULT = Path.home() / "Kaggle"

FALSE_VALUES = {"0", "false", "no", "off"}
TRUE_VALUES = {"1", "true", "yes", "on"}

KNOWN_EDITORS = {
    "code": {"cmd": "code", "name": "VS Code"},
    "cursor": {"cmd": "cursor", "name": "Cursor"},
    "zed": {"cmd": "zed", "name": "Zed"},
    "windsurf": {"cmd": "windsurf", "name": "Windsurf"},
    "jupyter": {"cmd": "jupyter", "name": "Jupyter Lab"},
}


@dataclass
class Config:
    kag_path: Path = KAG_PATH_DEFAULT
    default_editor: str | None = None
    auto_venv: bool = True
    auto_git: bool = True
    update_check: bool = True

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
                auto_git = data.get("auto_git", True)
                update_check = data.get("update_check", update_check)
                update_check = _env_update_check(update_check)
                return cls(
                    kag_path=kag_path,
                    default_editor=default_editor,
                    auto_venv=auto_venv,
                    auto_git=auto_git,
                    update_check=update_check,
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
