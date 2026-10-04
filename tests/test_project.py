from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from kag.config import Config
from kag.kaggle_api import Competition, CompetitionFile, DownloadResult, FileListResult
from kag import project
from kag.project import _extract_zip_safely


def _write_zip(zip_path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def test_extract_zip_safely_extracts_safe_nested_files(tmp_path: Path) -> None:
    zip_path = tmp_path / "safe.zip"
    data_dir = tmp_path / "data"
    _write_zip(
        zip_path,
        {
            "train.csv": "id,value\n1,2\n",
            "nested/test.csv": "id,value\n3,4\n",
        },
    )

    warnings = _extract_zip_safely(zip_path, data_dir)

    assert warnings == []
    assert (data_dir / "train.csv").read_text() == "id,value\n1,2\n"
    assert (data_dir / "nested" / "test.csv").read_text() == "id,value\n3,4\n"


def test_extract_zip_safely_skips_entries_that_escape_destination(tmp_path: Path) -> None:
    zip_path = tmp_path / "mixed.zip"
    data_dir = tmp_path / "data"
    _write_zip(
        zip_path,
        {
            "safe.csv": "safe\n",
            "../escape.txt": "escape\n",
            "nested/../../escape2.txt": "escape\n",
            "..\\escape3.txt": "escape\n",
            "/absolute.txt": "escape\n",
            "C:\\absolute.txt": "escape\n",
        },
    )

    warnings = _extract_zip_safely(zip_path, data_dir)

    assert (data_dir / "safe.csv").read_text() == "safe\n"
    assert not (tmp_path / "escape.txt").exists()
    assert not (tmp_path / "escape2.txt").exists()
    assert not (tmp_path / "escape3.txt").exists()
    assert len(warnings) == 5
    assert all("Skipped unsafe archive entry" in warning for warning in warnings)


def test_extract_zip_safely_rejects_symlink_escape_parents(tmp_path: Path) -> None:
    zip_path = tmp_path / "symlink-parent.zip"
    data_dir = tmp_path / "data"
    outside_dir = tmp_path / "outside"
    data_dir.mkdir()
    outside_dir.mkdir()
    try:
        (data_dir / "linked").symlink_to(outside_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    _write_zip(zip_path, {"linked/escape.txt": "escape\n"})

    warnings = _extract_zip_safely(zip_path, data_dir)

    assert not (outside_dir / "escape.txt").exists()
    assert len(warnings) == 1


def test_create_project_records_unsafe_zip_entries_in_notes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="unsafe-archive",
        title="Unsafe Archive",
        deadline="",
        reward="",
        team_count="0",
    )

    def fake_download_competition(slug: str, data_dir: str) -> bool:
        zip_path = Path(data_dir) / f"{slug}.zip"
        _write_zip(
            zip_path,
            {
                "train.csv": "safe\n",
                "../escape.txt": "escape\n",
            },
        )
        return DownloadResult(True, "Download completed", (f"{slug}.zip",))

    monkeypatch.setattr(
        project, "check_competition_access", lambda slug: (True, "Access confirmed")
    )
    monkeypatch.setattr(
        project,
        "list_competition_files",
        lambda slug: FileListResult(True, (CompetitionFile("train.csv", 123),)),
    )
    monkeypatch.setattr(project, "download_competition", fake_download_competition)
    monkeypatch.setattr(project, "get_competition_files", lambda slug: ["train.csv"])
    monkeypatch.setattr(project, "fetch_competition_markdown_sections", lambda slug: ({}, []))

    project_path = project.create_project(
        competition,
        Config(kag_path=tmp_path, auto_git=False, auto_venv=False),
    )

    assert project_path is not None
    notes = (Path(project_path) / "notes.md").read_text()
    assert "## Extraction Warnings" in notes
    assert "Skipped unsafe archive entry `../escape.txt` from `unsafe-archive.zip`." in notes
    assert (Path(project_path) / "data" / "train.csv").read_text() == "safe\n"
    assert not (tmp_path / "escape.txt").exists()


def test_create_project_raises_and_removes_new_project_after_download_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="forbidden-download",
        title="Forbidden Download",
        deadline="",
        reward="",
        team_count="0",
    )

    monkeypatch.setattr(
        project, "check_competition_access", lambda slug: (True, "Access confirmed")
    )
    monkeypatch.setattr(
        project,
        "list_competition_files",
        lambda slug: FileListResult(True, (CompetitionFile("train.csv", 123),)),
    )
    monkeypatch.setattr(
        project,
        "download_competition",
        lambda slug, data_dir: DownloadResult(False, "403 Client Error: Forbidden", ()),
    )
    monkeypatch.setattr(project, "fetch_competition_markdown_sections", lambda slug: ({}, []))

    with pytest.raises(project.ProjectCreationError, match="403 Client Error: Forbidden"):
        project.create_project(
            competition,
            Config(kag_path=tmp_path, auto_git=False, auto_venv=False),
        )

    assert not (tmp_path / "forbidden-download").exists()


def test_create_project_preserves_existing_project_after_download_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="existing-project",
        title="Existing Project",
        deadline="",
        reward="",
        team_count="0",
    )
    project_dir = tmp_path / competition.slug
    project_dir.mkdir()
    sentinel = project_dir / "keep.txt"
    sentinel.write_text("keep")

    monkeypatch.setattr(
        project, "check_competition_access", lambda slug: (True, "Access confirmed")
    )
    monkeypatch.setattr(
        project,
        "list_competition_files",
        lambda slug: FileListResult(True, (CompetitionFile("train.csv", 123),)),
    )
    monkeypatch.setattr(
        project,
        "download_competition",
        lambda slug, data_dir: DownloadResult(False, "403 Client Error: Forbidden", ()),
    )
    monkeypatch.setattr(project, "fetch_competition_markdown_sections", lambda slug: ({}, []))

    with pytest.raises(project.ProjectCreationError):
        project.create_project(
            competition,
            Config(kag_path=tmp_path, auto_git=False, auto_venv=False),
        )

    assert sentinel.read_text() == "keep"
    assert not (project_dir / "existing-project.ipynb").exists()
    assert not (project_dir / "notes.md").exists()


def test_create_project_does_not_open_editor_after_download_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="no-editor-on-failure",
        title="No Editor On Failure",
        deadline="",
        reward="",
        team_count="0",
    )
    popen_calls: list[object] = []

    monkeypatch.setattr(
        project, "check_competition_access", lambda slug: (True, "Access confirmed")
    )
    monkeypatch.setattr(
        project,
        "list_competition_files",
        lambda slug: FileListResult(True, (CompetitionFile("train.csv", 123),)),
    )
    monkeypatch.setattr(
        project,
        "download_competition",
        lambda slug, data_dir: DownloadResult(False, "403 Client Error: Forbidden", ()),
    )
    monkeypatch.setattr(project, "fetch_competition_markdown_sections", lambda slug: ({}, []))
    monkeypatch.setattr(project.shutil, "which", lambda cmd: "/usr/bin/code")
    monkeypatch.setattr(
        project.subprocess, "Popen", lambda *args, **kwargs: popen_calls.append(args)
    )

    with pytest.raises(project.ProjectCreationError):
        project.create_project(
            competition,
            Config(kag_path=tmp_path, auto_git=False, auto_venv=False),
            editor="code",
        )

    assert popen_calls == []


def test_create_project_without_download_still_creates_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="skip-download",
        title="Skip Download",
        deadline="",
        reward="",
        team_count="0",
    )
    download_calls: list[str] = []

    def fail_if_called(slug: str, data_dir: str) -> DownloadResult:
        download_calls.append(slug)
        return DownloadResult(False, "should not download", ())

    monkeypatch.setattr(project, "download_competition", fail_if_called)
    monkeypatch.setattr(project, "get_competition_files", lambda slug: ["train.csv"])
    monkeypatch.setattr(project, "fetch_competition_markdown_sections", lambda slug: ({}, []))

    project_path = project.create_project(
        competition,
        Config(kag_path=tmp_path, auto_git=False, auto_venv=False),
        download_files=False,
    )

    assert download_calls == []
    assert project_path is not None
    assert (Path(project_path) / "skip-download.ipynb").exists()
    assert (Path(project_path) / "notes.md").exists()


def test_create_project_skips_download_when_file_listing_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition = Competition(
        slug="no-data-competition",
        title="No Data Competition",
        deadline="",
        reward="",
        team_count="0",
    )
    download_calls: list[str] = []

    def fail_if_called(slug: str, data_dir: str) -> DownloadResult:
        download_calls.append(slug)
        return DownloadResult(False, "should not download", ())

    monkeypatch.setattr(
        project, "check_competition_access", lambda slug: (True, "Access confirmed")
    )
    monkeypatch.setattr(project, "list_competition_files", lambda slug: FileListResult(True, ()))
    monkeypatch.setattr(project, "download_competition", fail_if_called)
    monkeypatch.setattr(project, "fetch_competition_markdown_sections", lambda slug: ({}, []))

    project_path = project.create_project(
        competition,
        Config(kag_path=tmp_path, auto_git=False, auto_venv=False),
        download_files=True,
    )

    assert download_calls == []
    assert project_path is not None
    assert not (Path(project_path) / "data").exists()
    assert (Path(project_path) / "no-data-competition.ipynb").exists()
    assert (Path(project_path) / "notes.md").exists()


def _code_cell_sources(notebook: dict) -> list[str]:
    return ["".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"]


def _data_loading_source(files: list[str]) -> str:
    notebook = project.make_starter_notebook("demo", "", files)
    return _code_cell_sources(notebook)[1]


@pytest.mark.parametrize(
    "files",
    [
        ["train.csv", "test.csv", "sample_submission.csv"],
        ["test.csv", "sample_submission.csv"],
        ["2024-train.csv", "class.csv", "pd.csv", "my file (v2).csv"],
        ["train/labels.csv", "test/labels.csv", "train.csv.zip"],
        ["a².csv", "x½y.csv", "٣data.csv", "ﬁle.csv", "日本.csv"],
        ["images.zip", "metadata.json"],
        [],
    ],
)
def test_make_starter_notebook_code_cells_compile(files: list[str]) -> None:
    notebook = project.make_starter_notebook("demo", "", files)

    for source in _code_cell_sources(notebook):
        compile(source, "<cell>", "exec")


def test_make_starter_notebook_previews_train_when_present() -> None:
    source = _data_loading_source(["test.csv", "train.csv"])

    assert 'train = pd.read_csv(data_path + "train.csv")' in source
    assert source.endswith("train.head()")


def test_make_starter_notebook_previews_first_csv_without_train() -> None:
    source = _data_loading_source(["test.csv", "sample_submission.csv"])

    assert "train" not in source
    assert source.endswith("test.head()")


def test_make_starter_notebook_generates_unique_safe_variable_names() -> None:
    source = _data_loading_source(
        ["2024-test.csv", "class.csv", "pd.csv", "train/labels.csv", "test/labels.csv"]
    )

    assert 'df_2024_test = pd.read_csv(data_path + "2024-test.csv")' in source
    assert 'df_class = pd.read_csv(data_path + "class.csv")' in source
    assert 'df_pd = pd.read_csv(data_path + "pd.csv")' in source
    assert 'labels = pd.read_csv(data_path + "train/labels.csv")' in source
    assert 'labels_2 = pd.read_csv(data_path + "test/labels.csv")' in source


def test_make_starter_notebook_normalizes_unicode_variable_names() -> None:
    source = _data_loading_source(["a².csv", "x½y.csv", "٣data.csv", "ﬁle.csv", "file.csv"])

    assert 'a2 = pd.read_csv(data_path + "a².csv")' in source
    assert 'x1_2y = pd.read_csv(data_path + "x½y.csv")' in source
    assert 'df_٣data = pd.read_csv(data_path + "٣data.csv")' in source
    assert 'file = pd.read_csv(data_path + "ﬁle.csv")' in source
    assert 'file_2 = pd.read_csv(data_path + "file.csv")' in source


def test_make_starter_notebook_strips_zip_suffix_from_csv_archives() -> None:
    source = _data_loading_source(["train.csv.zip"])

    assert 'train = pd.read_csv(data_path + "train.csv")' in source


def test_make_starter_notebook_lists_data_dir_without_csv_files() -> None:
    source = _data_loading_source(["images.zip"])

    assert "read_csv" not in source
    assert "os.listdir(data_path)" in source


def test_make_starter_notebook_caps_csv_loads() -> None:
    files = [f"part_{index}.csv" for index in range(project.MAX_NOTEBOOK_CSV_LOADS + 5)]

    source = _data_loading_source(files)

    assert source.count("pd.read_csv") == project.MAX_NOTEBOOK_CSV_LOADS
    assert "# 5 more CSV files in data/" in source
