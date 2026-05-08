from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from kag.config import Config
from kag.kaggle_api import Competition
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
        return True

    monkeypatch.setattr(project, "ensure_competition_access", lambda slug: (True, "Access confirmed"))
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
