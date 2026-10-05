import json
import keyword
import re
import shutil
import subprocess
import threading
import unicodedata
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO

from .config import Config
from .kaggle_api import (
    Competition,
    check_competition_access,
    download_competition,
    get_competition_files,
    list_competition_files,
)
from . import context, environment, kaggle_sdk
from .environment import EnvironmentResult
from .kaggle_sdk import CompetitionDetails
from .notes_fetcher import fetch_competition_markdown_sections


class ProjectCreationError(RuntimeError):
    pass


class ProjectCreationCancelled(ProjectCreationError):
    pass


STARTER_NOTEBOOK = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11.0"},
    },
    "cells": [],
}


MAX_NOTEBOOK_CSV_LOADS = 10
EXTRACT_CHUNK_SIZE = 1024 * 1024
EDITOR_LOG_DIR = Path(".kag") / "logs"
RESERVED_NOTEBOOK_NAMES = {"pd", "np", "plt", "sns", "data_path", "train_test_split"}


def _csv_variable_name(file_name: str, used: set[str]) -> str:
    stem = PurePosixPath(file_name).name.removesuffix(".csv")
    normalized = unicodedata.normalize("NFKC", stem).lower()
    cleaned = "".join(char if f"_{char}".isidentifier() else "_" for char in normalized)
    base = re.sub(r"_+", "_", cleaned).strip("_") or "df"
    if not base.isidentifier() or keyword.iskeyword(base) or base in RESERVED_NOTEBOOK_NAMES:
        base = f"df_{base}"
    name = base
    suffix = 2
    while name in used:
        name = f"{base}_{suffix}"
        suffix += 1
    used.add(name)
    return name


def _data_loading_source(files: list[str]) -> str:
    csv_files = [
        name.replace("\\", "/").removesuffix(".zip")
        for name in files
        if name.removesuffix(".zip").lower().endswith(".csv")
    ]
    lines = ['data_path = "data/"']

    if not csv_files:
        lines.extend(["", "import os", "", "sorted(os.listdir(data_path))"])
        return "\n".join(lines)

    used: set[str] = set()
    variables: list[str] = []
    for csv_file in csv_files[:MAX_NOTEBOOK_CSV_LOADS]:
        variable = _csv_variable_name(csv_file, used)
        variables.append(variable)
        lines.append(
            f"{variable} = pd.read_csv(data_path + {json.dumps(csv_file, ensure_ascii=False)})"
        )

    remaining = len(csv_files) - MAX_NOTEBOOK_CSV_LOADS
    if remaining > 0:
        lines.append(f"# {remaining} more CSV files in data/")

    preview = "train" if "train" in variables else variables[0]
    lines.extend(["", f"{preview}.head()"])
    return "\n".join(lines)


def make_starter_notebook(competition_slug: str, description: str, files: list[str]) -> dict:
    nb = json.loads(json.dumps(STARTER_NOTEBOOK))

    nb["cells"].append(
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [f"# {competition_slug}\n\n{description or 'Kaggle competition notebook'}"],
        }
    )

    nb["cells"].append(
        {
            "cell_type": "code",
            "metadata": {},
            "source": [
                "import pandas as pd\nimport numpy as np\nimport matplotlib.pyplot as plt\nimport seaborn as sns\n\nfrom sklearn.model_selection import train_test_split\nfrom sklearn.preprocessing import StandardScaler\nfrom sklearn.metrics import mean_squared_error\n\nsns.set_style('whitegrid')\nprint('Setup complete')"
            ],
            "execution_count": None,
            "outputs": [],
        }
    )

    nb["cells"].append({"cell_type": "markdown", "metadata": {}, "source": ["## Data Loading"]})

    nb["cells"].append(
        {
            "cell_type": "code",
            "metadata": {},
            "source": [_data_loading_source(files)],
            "execution_count": None,
            "outputs": [],
        }
    )

    nb["cells"].append({"cell_type": "markdown", "metadata": {}, "source": ["## EDA"]})

    nb["cells"].append(
        {
            "cell_type": "code",
            "metadata": {},
            "source": [
                "# Explore the data\n# train.info()\n# train.describe()\n# train.isnull().sum()"
            ],
            "execution_count": None,
            "outputs": [],
        }
    )

    return nb


def _overview_snippet(sections: dict[str, str]) -> str:
    overview = sections.get("Overview", "")
    if not overview:
        return ""
    for line in overview.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("#"):
            continue
        if text.startswith("!"):
            continue
        return text[:220]
    return ""


def _details_lines(details: CompetitionDetails) -> list[str]:
    facts = [
        ("Category", details.category),
        ("Evaluation metric", details.evaluation_metric),
        ("Join deadline", details.new_entrant_deadline),
        ("Team merger deadline", details.merger_deadline),
        ("Max daily submissions", details.max_daily_submissions),
        ("Max team size", details.max_team_size),
        ("Submission type", "Notebook only" if details.is_kernels_submissions_only else ""),
        ("Submissions", "Disabled" if details.submissions_disabled else ""),
        ("Tags", ", ".join(details.tags)),
    ]
    return [f"**{label}:** {value}" for label, value in facts if value]


def make_notes_md(
    competition: Competition,
    files: list[str],
    sections: dict[str, str],
    warnings: list[str],
    access_note: str | None = None,
    details: CompetitionDetails | None = None,
) -> str:
    lines = [
        f"# {details.title if details else competition.title}",
        "",
    ]
    if details and details.description:
        lines.extend([details.description, ""])
    lines.extend(
        [
            f"**Slug:** {competition.slug}",
            f"**Deadline:** {details.deadline if details else competition.deadline}",
            f"**Reward:** {details.reward if details else competition.reward}",
            f"**Teams:** {details.team_count if details else competition.team_count}",
        ]
    )
    if details:
        lines.extend(_details_lines(details))

    if access_note:
        lines.extend(
            [
                "",
                f"**Access:** {access_note}",
            ]
        )

    if warnings:
        lines.extend(
            [
                "",
                "## Extraction Warnings",
            ]
        )
        for warning in warnings:
            lines.append(f"- {warning}")

    lines.extend(
        [
            "",
            "## Files",
        ]
    )
    for f in files:
        lines.append(f"- `{f}`")

    for section_name in ("Overview", "Evaluation", "Data", "Code", "Rules"):
        lines.extend(
            [
                "",
                f"## {section_name}",
                "",
            ]
        )
        content = sections.get(section_name, "")
        if content:
            lines.append(content)
        else:
            lines.append("_Not extracted automatically._")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "<!-- Your working notes -->",
        ]
    )
    return "\n".join(lines)


def _safe_zip_target(member_name: str, destination: Path) -> Path | None:
    normalized_name = member_name.replace("\\", "/")
    member_path = PurePosixPath(normalized_name)
    windows_path = PureWindowsPath(member_name)

    if (
        "\x00" in member_name
        or not member_path.parts
        or member_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or ".." in member_path.parts
    ):
        return None

    destination = destination.resolve()
    target = destination.joinpath(*member_path.parts).resolve()

    try:
        target.relative_to(destination)
    except ValueError:
        return None

    return target


def _copy_with_cancel(source: BinaryIO, output: BinaryIO, cancel: threading.Event | None) -> None:
    while True:
        if cancel is not None and cancel.is_set():
            raise ProjectCreationCancelled("Project setup cancelled")
        chunk = source.read(EXTRACT_CHUNK_SIZE)
        if not chunk:
            return
        output.write(chunk)


def _extract_zip_safely(
    zip_path: Path,
    destination: Path,
    cancel: threading.Event | None = None,
) -> list[str]:
    warnings: list[str] = []
    destination.mkdir(parents=True, exist_ok=True)

    kept_existing: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            target = _safe_zip_target(member.filename, destination)
            if target is None:
                warnings.append(
                    f"Skipped unsafe archive entry `{member.filename}` from `{zip_path.name}`."
                )
                continue

            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                output = target.open("xb")
            except FileExistsError:
                kept_existing.append(member.filename)
                continue
            with archive.open(member, "r") as source, output:
                _copy_with_cancel(source, output, cancel)

    if kept_existing:
        warnings.append(
            f"Kept {len(kept_existing)} existing file(s) instead of overwriting them from "
            f"`{zip_path.name}` (e.g. `{kept_existing[0]}`). Delete a file to extract it again."
        )
    return warnings


def _editor_command(editor: str, project_dir: Path, notebook_path: Path) -> list[str]:
    if editor == "jupyter-lab":
        return ["jupyter-lab", str(notebook_path)]
    return [editor, str(project_dir)]


def _editor_log_path(project_dir: Path, editor: str) -> Path:
    return project_dir / EDITOR_LOG_DIR / f"{Path(editor).name}.log"


def _download_failure_message(slug: str, details: str) -> str:
    message = f"Download failed for {slug}: {details}"
    if "403" in details or "forbidden" in details.lower():
        message += " Join the competition and accept its rules on Kaggle, then retry the download."
    return message


def existing_project_dir(config: Config, slug: str) -> Path | None:
    project_dir = config.kag_path / slug
    try:
        if project_dir.is_dir() and any(project_dir.iterdir()):
            return project_dir
    except OSError:
        return None
    return None


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _remove_new_paths(directory: Path, existing: set[Path]) -> None:
    for path in sorted(directory.rglob("*"), reverse=True):
        if path in existing:
            continue
        try:
            if path.is_dir() and not path.is_symlink():
                path.rmdir()
            else:
                path.unlink()
        except OSError:
            continue


def fetch_competition_details(slug: str) -> CompetitionDetails | None:
    try:
        return kaggle_sdk.get_competition_details(slug)
    except kaggle_sdk.KaggleSdkError:
        return None


def _write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return True


def _write_generated(path: Path, content: str, previous_hash: str | None) -> bool:
    if not path.exists():
        return _write_if_missing(path, content)
    try:
        current = path.read_text()
    except OSError:
        return False
    if current == content:
        return True
    if previous_hash is None or context.content_hash(current) != previous_hash:
        return False
    path.write_text(content)
    return True


def _write_agent_context(
    project_dir: Path,
    competition: Competition,
    details: CompetitionDetails | None,
    listed_files: list[str],
    notebook_name: str,
    cancel: threading.Event | None = None,
    pyproject_written: bool = False,
) -> None:
    data_profile = context.profile_data(project_dir / "data", listed_files, cancel)
    if cancel is not None and cancel.is_set():
        raise ProjectCreationCancelled("Project setup cancelled")
    manifest = context.build_manifest(competition, details, data_profile, notebook_name)
    title = details.title if details else competition.title
    previous = context.generated_hashes(project_dir)
    has_pyproject = (project_dir / environment.PYPROJECT_NAME).exists()
    outputs = {"AGENTS.md": context.render_agents_md(manifest, has_pyproject)}
    if data_profile.downloaded:
        outputs[context.SCHEMA_PATH.as_posix()] = context.render_schema_md(title, data_profile)
    owned: dict[str, str] = {}
    for name, content in outputs.items():
        if _write_generated(project_dir / name, content, previous.get(name)):
            owned[name] = context.content_hash(content)
    pyproject = project_dir / environment.PYPROJECT_NAME
    if pyproject.exists():
        current = context.content_hash(pyproject.read_text())
        if pyproject_written or previous.get(environment.PYPROJECT_NAME) == current:
            owned[environment.PYPROJECT_NAME] = current
    manifest["generated_files"] = owned
    manifest_path = project_dir / context.MANIFEST_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(context.manifest_json(manifest))
    _write_if_missing(project_dir / "CLAUDE.md", "@AGENTS.md\n")


def create_project(
    competition: Competition,
    config: Config,
    download_files: bool = True,
    editor: str | None = None,
    progress: Callable[[str], None] | None = None,
    cancel: threading.Event | None = None,
    details: CompetitionDetails | None = None,
    install_environment: bool | None = None,
    on_environment: Callable[[EnvironmentResult], None] | None = None,
) -> str | None:
    def report(message: str) -> None:
        if progress is not None:
            progress(message)

    def check_cancel() -> None:
        if cancel is not None and cancel.is_set():
            raise ProjectCreationCancelled("Project setup cancelled")

    project_dir = config.kag_path / competition.slug
    project_existed = project_dir.exists()
    project_had_content = existing_project_dir(config, competition.slug) is not None
    existing_paths = set(project_dir.rglob("*")) if project_existed else set()
    project_dir.mkdir(parents=True, exist_ok=True)

    try:
        check_cancel()
        if details is None:
            report("Fetching competition details...")
            details = fetch_competition_details(competition.slug)
            check_cancel()
        report("Fetching competition notes...")
        sections, extract_warnings = fetch_competition_markdown_sections(
            competition.slug, cancel=cancel
        )
        check_cancel()
        access_note = None
        download_permitted = download_files
        listed_files: list[str] | None = None

        if download_files:
            report("Checking access and data files...")
            access_ok, access_details = check_competition_access(competition.slug)
            if not access_ok:
                raise ProjectCreationError(
                    _download_failure_message(competition.slug, access_details)
                )
            file_list = list_competition_files(competition.slug)
            if file_list.success:
                listed_files = [file.name for file in file_list.files]
                if not listed_files:
                    download_permitted = False

        check_cancel()
        if download_permitted:
            data_dir = project_dir / "data"
            data_dir.mkdir(exist_ok=True)
            report("Downloading data...")
            download_result = download_competition(
                competition.slug,
                str(data_dir),
                progress=lambda size: report(f"Downloading data... {format_bytes(size)}"),
                cancel=cancel,
            )
            if not download_result.success:
                if download_result.cancelled:
                    raise ProjectCreationCancelled("Project setup cancelled")
                raise ProjectCreationError(
                    _download_failure_message(competition.slug, download_result.details)
                )

            zip_files = list(data_dir.glob("*.zip"))
            for zf in zip_files:
                check_cancel()
                report(f"Extracting {zf.name}...")
                extract_warnings.extend(_extract_zip_safely(zf, data_dir, cancel=cancel))

        if listed_files is not None:
            files = listed_files
        else:
            files = (
                get_competition_files(competition.slug)
                if (download_permitted or not download_files)
                else []
            )

        check_cancel()
        report("Writing notebook and notes...")
        notebook_description = _overview_snippet(sections)

        notebook = make_starter_notebook(competition.slug, notebook_description, files)
        notebook_path = project_dir / f"{competition.slug}.ipynb"
        _write_if_missing(notebook_path, json.dumps(notebook, indent=1))

        notes = make_notes_md(
            competition=competition,
            files=files,
            sections=sections,
            warnings=extract_warnings,
            access_note=access_note,
            details=details,
        )
        _write_if_missing(project_dir / "notes.md", notes)

        pyproject_written = environment.write_pyproject(project_dir, competition.slug, config)

        check_cancel()
        report("Writing agent context files...")
        _write_agent_context(
            project_dir,
            competition,
            details,
            files,
            notebook_path.name,
            cancel,
            pyproject_written=pyproject_written,
        )

        check_cancel()
        environment_result = environment.setup_environment(
            project_dir,
            config,
            environment.wants_install(config, install_environment),
            check_cancel,
            report,
        )
        if on_environment is not None:
            on_environment(environment_result)

        check_cancel()
        if config.auto_git and not project_had_content:
            report("Setting up git...")
            try:
                subprocess.run(
                    ["git", "init"], cwd=str(project_dir), capture_output=True, timeout=10
                )
                gitignore = project_dir / ".gitignore"
                gitignore.write_text(
                    ".venv/\n__pycache__/\n*.pyc\n.ipynb_checkpoints/\ndata/\n"
                    f"{EDITOR_LOG_DIR.as_posix()}/\n"
                )
                subprocess.run(
                    ["git", "add", "-A"], cwd=str(project_dir), capture_output=True, timeout=10
                )
                subprocess.run(
                    ["git", "commit", "-m", "Initial commit from kag"],
                    cwd=str(project_dir),
                    capture_output=True,
                    timeout=10,
                )
            except Exception:
                pass

        check_cancel()
        if editor and shutil.which(editor):
            report(f"Opening {editor}...")
            log_path = _editor_log_path(project_dir, editor)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("ab") as log_file:
                subprocess.Popen(
                    _editor_command(editor, project_dir, notebook_path),
                    cwd=str(project_dir),
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )

        return str(project_dir)
    except Exception:
        if project_existed:
            _remove_new_paths(project_dir, existing_paths)
        else:
            shutil.rmtree(project_dir, ignore_errors=True)
        raise
