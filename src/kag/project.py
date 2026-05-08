import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from .config import Config
from .kaggle_api import (
    Competition,
    download_competition,
    ensure_competition_access,
    get_competition_files,
)
from .notes_fetcher import fetch_competition_markdown_sections


STARTER_NOTEBOOK = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "name": "python",
            "version": "3.11.0"
        }
    },
    "cells": []
}


def make_starter_notebook(competition_slug: str, description: str, files: list[str]) -> dict:
    nb = json.loads(json.dumps(STARTER_NOTEBOOK))

    nb["cells"].append({
        "cell_type": "markdown",
        "metadata": {},
        "source": [f"# {competition_slug}\n\n{description or 'Kaggle competition notebook'}"]
    })

    nb["cells"].append({
        "cell_type": "code",
        "metadata": {},
        "source": [
            "import pandas as pd\nimport numpy as np\nimport matplotlib.pyplot as plt\nimport seaborn as sns\n\nfrom sklearn.model_selection import train_test_split\nfrom sklearn.preprocessing import StandardScaler\nfrom sklearn.metrics import mean_squared_error\n\nsns.set_style('whitegrid')\nprint('Setup complete')"
        ],
        "execution_count": None,
        "outputs": []
    })

    data_path = '"data/"'
    nb["cells"].append({
        "cell_type": "markdown",
        "metadata": {},
        "source": ["## Data Loading"]
    })

    load_lines = [f'data_path = {data_path}']
    for f in files:
        clean = f.replace(".zip", "").replace(".csv.zip", ".csv")
        if clean.endswith(".csv"):
            var_name = Path(clean).stem.replace("-", "_").replace(" ", "_")
            load_lines.append(f'{var_name} = pd.read_csv(data_path + "{clean}")')
    load_lines.append("train.head()")

    nb["cells"].append({
        "cell_type": "code",
        "metadata": {},
        "source": load_lines,
        "execution_count": None,
        "outputs": []
    })

    nb["cells"].append({
        "cell_type": "markdown",
        "metadata": {},
        "source": ["## EDA"]
    })

    nb["cells"].append({
        "cell_type": "code",
        "metadata": {},
        "source": [
            "# Explore the data\n# train.info()\n# train.describe()\n# train.isnull().sum()"
        ],
        "execution_count": None,
        "outputs": []
    })

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


def make_notes_md(
    competition: Competition,
    files: list[str],
    sections: dict[str, str],
    warnings: list[str],
    access_note: str | None = None,
) -> str:
    lines = [
        f"# {competition.title}",
        "",
        f"**Slug:** {competition.slug}",
        f"**Deadline:** {competition.deadline}",
        f"**Reward:** {competition.reward}",
        f"**Teams:** {competition.team_count}",
    ]

    if access_note:
        lines.extend([
            "",
            f"**Access:** {access_note}",
        ])

    if warnings:
        lines.extend([
            "",
            "## Extraction Warnings",
        ])
        for warning in warnings:
            lines.append(f"- {warning}")

    lines.extend([
        "",
        "## Files",
    ])
    for f in files:
        lines.append(f"- `{f}`")

    for section_name in ("Overview", "Evaluation", "Data", "Code", "Rules"):
        lines.extend([
            "",
            f"## {section_name}",
            "",
        ])
        content = sections.get(section_name, "")
        if content:
            lines.append(content)
        else:
            lines.append("_Not extracted automatically._")

    lines.extend([
        "",
        "## Notes",
        "",
        "<!-- Your working notes -->",
    ])
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


def _extract_zip_safely(zip_path: Path, destination: Path) -> list[str]:
    warnings: list[str] = []
    destination.mkdir(parents=True, exist_ok=True)

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
            with archive.open(member, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)

    return warnings


def create_project(
    competition: Competition,
    config: Config,
    download_files: bool = True,
    editor: str | None = None,
) -> str | None:
    project_dir = config.kag_path / competition.slug
    project_dir.mkdir(parents=True, exist_ok=True)

    sections, extract_warnings = fetch_competition_markdown_sections(competition.slug)
    access_note = None
    download_permitted = download_files

    if download_files:
        access_ok, access_details = ensure_competition_access(competition.slug)
        if not access_ok:
            download_permitted = False
            access_note = (
                "Competition access could not be confirmed automatically. "
                f"Reason: {access_details}. Open Kaggle overview/rules and accept terms, then retry download."
            )

    if download_permitted:
        data_dir = project_dir / "data"
        data_dir.mkdir(exist_ok=True)
        downloaded = download_competition(competition.slug, str(data_dir))
        if not downloaded:
            access_note = (
                "Download did not complete. Ensure you joined the competition and accepted rules, "
                "then run kaggle competitions download manually."
            )

        if downloaded:
            zip_files = list(data_dir.glob("*.zip"))
            for zf in zip_files:
                extract_warnings.extend(_extract_zip_safely(zf, data_dir))

    files = get_competition_files(competition.slug) if (download_permitted or not download_files) else []

    notebook_description = _overview_snippet(sections)

    notebook = make_starter_notebook(competition.slug, notebook_description, files)
    notebook_path = project_dir / f"{competition.slug}.ipynb"
    with open(notebook_path, "w") as f:
        json.dump(notebook, f, indent=1)

    notes = make_notes_md(
        competition=competition,
        files=files,
        sections=sections,
        warnings=extract_warnings,
        access_note=access_note,
    )
    notes_path = project_dir / "notes.md"
    notes_path.write_text(notes)

    if config.auto_git:
        try:
            subprocess.run(["git", "init"], cwd=str(project_dir), capture_output=True, timeout=10)
            gitignore = project_dir / ".gitignore"
            gitignore.write_text(".venv/\n__pycache__/\n*.pyc\n.ipynb_checkpoints/\ndata/\n")
            subprocess.run(["git", "add", "-A"], cwd=str(project_dir), capture_output=True, timeout=10)
            subprocess.run(["git", "commit", "-m", "Initial commit from kag"], cwd=str(project_dir), capture_output=True, timeout=10)
        except Exception:
            pass

    if config.auto_venv:
        try:
            subprocess.run([sys.executable, "-m", "venv", ".venv"], cwd=str(project_dir), capture_output=True, timeout=30)
        except Exception:
            pass

    if editor and shutil.which(editor):
        subprocess.Popen([editor, str(project_dir)], start_new_session=True)
    elif editor == "jupyter" and shutil.which("jupyter"):
        nb_path = str(notebook_path)
        subprocess.Popen(["jupyter", "lab", nb_path], cwd=str(project_dir), start_new_session=True)

    return str(project_dir)
