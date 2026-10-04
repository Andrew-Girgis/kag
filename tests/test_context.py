from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from kag import context, project
from kag.config import Config
from kag.kaggle_api import Competition, CompetitionFile, DownloadResult, FileListResult
from kag.kaggle_sdk import CompetitionDetails

TRAIN = "PassengerId,Survived,Name,Age,Fare,Embarked,Boarded\n1,0,Braund,22,7.25,S,2026-01-01\n2,1,Cumings,,71.28,C,2026-01-02\n"
TEST = "PassengerId,Name,Age,Fare,Embarked,Boarded\n892,Kelly,34.5,7.83,Q,2026-01-03\n"
SAMPLE = "PassengerId,Survived\n892,0\n893,1"


def _competition() -> Competition:
    return Competition(
        slug="titanic", title="titanic", deadline="2030-01-01", reward="Knowledge", team_count="0"
    )


def _details(**overrides: object) -> CompetitionDetails:
    values: dict[str, object] = {
        "slug": "titanic",
        "title": "Titanic - Machine Learning from Disaster",
        "description": "Predict survival on the Titanic",
        "evaluation_metric": "Categorization Accuracy",
        "max_daily_submissions": 10,
        "max_team_size": 10,
        "deadline": "2030-01-01 00:00:00",
        "url": "https://www.kaggle.com/competitions/titanic",
        "tags": ("tabular",),
    }
    values.update(overrides)
    return CompetitionDetails(**values)  # type: ignore[arg-type]


@pytest.fixture
def titanic_data(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "train.csv").write_text(TRAIN)
    (data_dir / "test.csv").write_text(TEST)
    (data_dir / "sample_submission.csv").write_text(SAMPLE)
    (data_dir / "titanic.zip").write_bytes(b"zip")
    (data_dir / "images").mkdir()
    (data_dir / "images" / "a.png").write_bytes(b"png")
    return data_dir


def test_profile_csv_infers_types_missing_values_and_rows(titanic_data: Path) -> None:
    profile = context.profile_csv(titanic_data / "train.csv", titanic_data)

    columns = {column.name: column for column in profile.columns}
    assert profile.rows == 2
    assert columns["PassengerId"].type == "integer"
    assert columns["Age"].type == "integer"
    assert columns["Age"].missing_in_sample == 1
    assert columns["Fare"].type == "float"
    assert columns["Name"].type == "string"
    assert columns["Boarded"].type == "datetime"
    assert columns["Name"].examples == ["Braund", "Cumings"]


def test_estimate_rows_handles_missing_trailing_newline(titanic_data: Path) -> None:
    assert context._estimate_rows(titanic_data / "sample_submission.csv") == 2


def test_profile_data_finds_submission_columns_and_skips_archives(titanic_data: Path) -> None:
    data = context.profile_data(titanic_data, [])

    assert data.downloaded is True
    assert data.sample_submission == "sample_submission.csv"
    assert data.id_column == "PassengerId"
    assert data.target_columns == ["Survived"]
    assert data.submission_rows == 2
    paths = [profile.path for profile in data.files]
    assert "titanic.zip" not in paths
    image = next(profile for profile in data.files if profile.path == "images/a.png")
    assert image.inspected is False


def test_profile_data_infers_target_from_train_test_difference(titanic_data: Path) -> None:
    (titanic_data / "sample_submission.csv").unlink()

    data = context.profile_data(titanic_data, [])

    assert data.id_column is None
    assert data.target_columns == ["Survived"]


def test_profile_data_without_download(tmp_path: Path) -> None:
    data = context.profile_data(tmp_path / "data", ["train.csv"])

    assert data.downloaded is False
    assert data.listed_files == ["train.csv"]


def test_schema_md_describes_each_file(titanic_data: Path) -> None:
    schema = context.render_schema_md("Titanic", context.profile_data(titanic_data, []))

    assert schema.startswith("# Data schema: Titanic")
    assert "- **ID column:** `PassengerId`" in schema
    assert "- **Target column(s):** `Survived`" in schema
    assert "## `train.csv`" in schema
    assert "| `Age` | integer | 1 | `22` |" in schema
    assert "## `images/a.png`" in schema
    assert "_Not inspected (only CSV files are profiled)._" in schema


def test_manifest_combines_details_and_data(titanic_data: Path) -> None:
    data = context.profile_data(titanic_data, ["train.csv"])

    manifest = context.build_manifest(_competition(), _details(), data, "titanic.ipynb")

    assert manifest["schema_version"] == 1
    assert manifest["competition"]["title"] == "Titanic - Machine Learning from Disaster"
    assert manifest["competition"]["evaluation_metric"] == "Categorization Accuracy"
    assert manifest["competition"]["max_daily_submissions"] == 10
    assert manifest["competition"]["tags"] == ["tabular"]
    assert manifest["submission"] == {
        "template": "data/sample_submission.csv",
        "id_column": "PassengerId",
        "target_columns": ["Survived"],
        "rows": 2,
    }
    train = next(f for f in manifest["data"]["files"] if f["path"] == "data/train.csv")
    assert train["columns"][:2] == ["PassengerId", "Survived"]
    json.dumps(manifest)


def test_manifest_without_details_uses_listing_fields(tmp_path: Path) -> None:
    data = context.profile_data(tmp_path / "data", [])

    manifest = context.build_manifest(_competition(), None, data, "titanic.ipynb")

    assert manifest["competition"]["title"] == "titanic"
    assert manifest["competition"]["url"] == "https://www.kaggle.com/competitions/titanic"
    assert manifest["competition"]["evaluation_metric"] == ""


def test_agents_md_for_csv_competition(titanic_data: Path) -> None:
    manifest = context.build_manifest(
        _competition(), _details(), context.profile_data(titanic_data, []), "titanic.ipynb"
    )

    agents = context.render_agents_md(manifest)

    assert agents.startswith("# Titanic - Machine Learning from Disaster")
    assert "- **Evaluation metric:** Categorization Accuracy" in agents
    assert "- **Daily submission limit:** 10" in agents
    assert "- **Submission type:** CSV file upload" in agents
    assert (
        "Match `data/sample_submission.csv`: columns `PassengerId`, `Survived`, 2 rows." in agents
    )
    assert 'kaggle competitions submit -c titanic -f <file> -m "<message>"' in agents
    assert "see `data/SCHEMA.md`" in agents


def test_agents_md_for_notebook_only_competition_without_data(tmp_path: Path) -> None:
    manifest = context.build_manifest(
        _competition(),
        _details(is_kernels_submissions_only=True),
        context.profile_data(tmp_path / "data", []),
        "titanic.ipynb",
    )

    agents = context.render_agents_md(manifest)

    assert "Kaggle notebook only (code competition)" in agents
    assert "Submit by running a Kaggle notebook attached to the competition." in agents
    assert "kaggle competitions download -c titanic -p data" in agents
    assert "See the Evaluation section of `notes.md`." in agents


def test_create_project_writes_agent_context_without_overwriting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(project, "get_competition_files", lambda slug: ["train.csv"])
    monkeypatch.setattr(
        project, "fetch_competition_markdown_sections", lambda slug, **kwargs: ({}, [])
    )
    monkeypatch.setattr(project, "fetch_competition_details", lambda slug: _details())
    project_dir = tmp_path / "titanic"
    (project_dir / "data").mkdir(parents=True)
    (project_dir / "data" / "train.csv").write_text(TRAIN)
    (project_dir / "CLAUDE.md").write_text("MY CLAUDE NOTES")

    project.create_project(
        _competition(),
        Config(kag_path=tmp_path, auto_git=False, auto_venv=False),
        download_files=False,
    )

    assert (project_dir / "CLAUDE.md").read_text() == "MY CLAUDE NOTES"
    assert (project_dir / "AGENTS.md").read_text().startswith("# Titanic - Machine Learning")
    assert (project_dir / "data" / "SCHEMA.md").read_text().startswith("# Data schema:")
    manifest = json.loads((project_dir / ".kag" / "competition.json").read_text())
    assert manifest["competition"]["slug"] == "titanic"


def test_create_project_writes_claude_md_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project, "get_competition_files", lambda slug: [])
    monkeypatch.setattr(
        project, "fetch_competition_markdown_sections", lambda slug, **kwargs: ({}, [])
    )

    project_path = project.create_project(
        _competition(),
        Config(kag_path=tmp_path, auto_git=False, auto_venv=False),
        download_files=False,
    )

    assert (Path(project_path) / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    assert not (Path(project_path) / "data").exists()


def test_gitignore_keeps_schema_but_ignores_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "fresh"
    competition = Competition(slug="fresh", title="Fresh", deadline="", reward="", team_count="0")

    def fake_download(slug: str, data_dir: str, **kwargs: object) -> DownloadResult:
        (Path(data_dir) / "train.csv").write_text(TRAIN)
        return DownloadResult(True, "Download completed", ("train.csv",))

    monkeypatch.setattr(
        project, "fetch_competition_markdown_sections", lambda slug, **kwargs: ({}, [])
    )
    monkeypatch.setattr(project, "check_competition_access", lambda slug: (True, "ok"))
    monkeypatch.setattr(
        project,
        "list_competition_files",
        lambda slug: FileListResult(True, (CompetitionFile("train.csv", 10),)),
    )
    monkeypatch.setattr(project, "download_competition", fake_download)

    project.create_project(competition, Config(kag_path=tmp_path, auto_git=True, auto_venv=False))

    ignored = subprocess.run(
        ["git", "check-ignore", "data/train.csv", "data/SCHEMA.md"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert ignored == ["data/train.csv"]
    staged = subprocess.run(
        ["git", "ls-files"], cwd=project_dir, capture_output=True, text=True
    ).stdout.split()
    assert {"data/SCHEMA.md", "AGENTS.md", "CLAUDE.md", ".kag/competition.json"} <= set(staged)


def test_rows_count_csv_records_not_newlines(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "notes.csv").write_text('id,text\n1,"line one\nline two"\n')

    profile = context.profile_csv(data_dir / "notes.csv", data_dir)

    assert profile.rows == 1
    assert profile.rows_estimated is False


def test_large_files_get_estimated_row_counts(
    titanic_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(context, "MAX_EXACT_COUNT_BYTES", 1)

    data = context.profile_data(titanic_data, [])
    train = next(profile for profile in data.files if profile.path == "train.csv")

    assert train.rows == 2
    assert train.rows_estimated is True
    assert data.submission_rows is None
    assert "~2 rows (estimated from line count)" in context.render_schema_md("T", data)


def test_submission_csv_is_profiled_even_after_many_other_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(context, "MAX_INSPECTED_CSVS", 2)
    data_dir = tmp_path / "data"
    (data_dir / "images").mkdir(parents=True)
    for index in range(5):
        (data_dir / f"aaa_{index}.csv").write_text("x\n1\n")
        (data_dir / "images" / f"{index}.png").write_bytes(b"png")
    (data_dir / "sample_submission.csv").write_text(SAMPLE)

    data = context.profile_data(data_dir, [])

    assert data.sample_submission == "sample_submission.csv"
    assert data.id_column == "PassengerId"
    assert data.target_columns == ["Survived"]
    assert sum(1 for profile in data.files if profile.inspected) == 2


def test_huge_datasets_are_summarized_not_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(context, "MAX_LISTED_FILES", 5)
    data_dir = tmp_path / "data"
    (data_dir / "images").mkdir(parents=True)
    (data_dir / "sample_submission.csv").write_text(SAMPLE)
    for index in range(20):
        (data_dir / "images" / f"{index:03}.png").write_bytes(b"x" * 10)
    for index in range(3):
        (data_dir / "images" / f"{index:03}.jpg").write_bytes(b"x" * 10)

    data = context.profile_data(data_dir, [])
    schema = context.render_schema_md("Images", data)
    manifest = context.build_manifest(_competition(), None, data, "x.ipynb")

    assert len(data.files) == 5
    assert data.omitted_files == 19
    assert "_...and 19 more files (190 B) not listed: `.png` x18, `.jpg` x1._" in schema
    assert len(manifest["data"]["files"]) == 5
    assert manifest["data"]["omitted_files"] == {
        "count": 19,
        "size_bytes": 190,
        "extensions": {".jpg": 1, ".png": 18},
    }


def test_agents_md_for_disabled_submissions(titanic_data: Path) -> None:
    manifest = context.build_manifest(
        _competition(),
        _details(submissions_disabled=True),
        context.profile_data(titanic_data, []),
        "titanic.ipynb",
    )

    agents = context.render_agents_md(manifest)

    assert "- **Submission type:** Disabled" in agents
    assert "Submissions are disabled for this competition" in agents
    assert "kaggle competitions submit" not in agents
