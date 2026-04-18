import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import Config
from .kaggle_api import Competition, download_competition, get_competition_files


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

    data_path = f'"data/"'
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


def make_notes_md(competition: Competition, files: list[str]) -> str:
    lines = [
        f"# {competition.title}",
        "",
        f"**Slug:** {competition.slug}",
        f"**Deadline:** {competition.deadline}",
        f"**Reward:** {competition.reward}",
        f"**Teams:** {competition.team_count}",
        "",
        "## Files",
    ]
    for f in files:
        lines.append(f"- `{f}`")
    lines.extend([
        "",
        "## Objective",
        "",
        "<!-- Describe the competition objective here -->",
        "",
        "## Evaluation",
        "",
        "<!-- Describe the evaluation metric here -->",
        "",
        "## Notes",
        "",
        "<!-- Your working notes -->",
    ])
    return "\n".join(lines)


def create_project(
    competition: Competition,
    config: Config,
    download_files: bool = True,
    editor: str | None = None,
) -> str | None:
    project_dir = config.kag_path / competition.slug
    project_dir.mkdir(parents=True, exist_ok=True)

    if download_files:
        data_dir = project_dir / "data"
        data_dir.mkdir(exist_ok=True)
        download_competition(competition.slug, str(data_dir))

        zip_files = list(data_dir.glob("*.zip"))
        for zf in zip_files:
            import zipfile
            with zipfile.ZipFile(zf, "r") as z:
                z.extractall(data_dir)

    files = get_competition_files(competition.slug) if download_files else []

    notebook = make_starter_notebook(competition.slug, "", files)
    notebook_path = project_dir / f"{competition.slug}.ipynb"
    with open(notebook_path, "w") as f:
        json.dump(notebook, f, indent=1)

    notes = make_notes_md(competition, files)
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