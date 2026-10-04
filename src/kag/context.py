from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .kaggle_api import Competition
from .kaggle_sdk import CompetitionDetails

MANIFEST_PATH = Path(".kag") / "competition.json"
SCHEMA_PATH = Path("data") / "SCHEMA.md"
MANIFEST_SCHEMA_VERSION = 1
SAMPLE_ROWS = 1000
EXAMPLE_VALUES = 3
MAX_INSPECTED_CSVS = 50
MAX_LISTED_FILES = 200
MAX_EXACT_COUNT_BYTES = 128 * 1024 * 1024
MAX_ESTIMATED_COUNT_BYTES = 512 * 1024 * 1024
COUNT_CHUNK_SIZE = 1024 * 1024
PRIORITY_STEMS = ("sample_submission", "gender_submission", "train", "test")


@dataclass
class ColumnProfile:
    name: str
    type: str
    missing_in_sample: int
    examples: list[str]


@dataclass
class DataFileProfile:
    path: str
    size_bytes: int
    rows: int | None = None
    rows_estimated: bool = False
    columns: list[ColumnProfile] = field(default_factory=list)
    inspected: bool = False


@dataclass
class DataProfile:
    downloaded: bool
    files: list[DataFileProfile]
    listed_files: list[str]
    id_column: str | None = None
    target_columns: list[str] = field(default_factory=list)
    sample_submission: str | None = None
    submission_rows: int | None = None
    omitted_files: int = 0
    omitted_bytes: int = 0
    omitted_extensions: dict[str, int] = field(default_factory=dict)


def _value_type(value: str) -> str:
    text = value.strip()
    if text.lower() in {"true", "false"}:
        return "boolean"
    try:
        int(text)
        return "integer"
    except ValueError:
        pass
    try:
        float(text)
        return "float"
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            datetime.strptime(text[:19], pattern)
            return "datetime"
        except ValueError:
            continue
    return "string"


def _column_type(values: list[str]) -> str:
    kinds = {_value_type(value) for value in values if value.strip()}
    if not kinds:
        return "empty"
    if kinds == {"integer", "float"}:
        return "float"
    if len(kinds) == 1:
        return kinds.pop()
    return "string"


def _estimate_rows(path: Path) -> int | None:
    if path.stat().st_size > MAX_ESTIMATED_COUNT_BYTES:
        return None
    newlines = 0
    last = b"\n"
    with path.open("rb") as handle:
        while chunk := handle.read(COUNT_CHUNK_SIZE):
            newlines += chunk.count(b"\n")
            last = chunk[-1:]
    lines = newlines + (0 if last == b"\n" else 1)
    return max(0, lines - 1)


def profile_csv(path: Path, data_dir: Path) -> DataFileProfile:
    profile = DataFileProfile(
        path=path.relative_to(data_dir).as_posix(),
        size_bytes=path.stat().st_size,
    )
    count_exactly = profile.size_bytes <= MAX_EXACT_COUNT_BYTES
    records = 0
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if not header:
                return profile
            samples: list[list[str]] = [[] for _ in header]
            for row in reader:
                if records < SAMPLE_ROWS:
                    for position in range(len(header)):
                        samples[position].append(row[position] if position < len(row) else "")
                elif not count_exactly:
                    break
                records += 1
    except (OSError, csv.Error):
        return profile

    profile.columns = [
        ColumnProfile(
            name=name,
            type=_column_type(values),
            missing_in_sample=sum(1 for value in values if not value.strip()),
            examples=[value for value in values if value.strip()][:EXAMPLE_VALUES],
        )
        for name, values in zip(header, samples)
    ]
    if count_exactly:
        profile.rows = records
    else:
        profile.rows = _estimate_rows(path)
        profile.rows_estimated = profile.rows is not None
    profile.inspected = True
    return profile


def _find(profiles: list[DataFileProfile], stem: str) -> DataFileProfile | None:
    for profile in profiles:
        if Path(profile.path).stem.lower() == stem:
            return profile
    return None


def _csv_priority(path: Path) -> tuple[int, str]:
    stem = path.stem.lower()
    rank = PRIORITY_STEMS.index(stem) if stem in PRIORITY_STEMS else len(PRIORITY_STEMS)
    return rank, path.as_posix()


def profile_data(data_dir: Path, listed_files: list[str]) -> DataProfile:
    if not data_dir.is_dir():
        return DataProfile(downloaded=False, files=[], listed_files=listed_files)

    paths = sorted(
        path
        for path in data_dir.rglob("*")
        if path.is_file() and path.name != SCHEMA_PATH.name and path.suffix.lower() != ".zip"
    )
    csv_paths = sorted((path for path in paths if path.suffix.lower() == ".csv"), key=_csv_priority)
    inspected = set(csv_paths[:MAX_INSPECTED_CSVS])

    profiles = [profile_csv(path, data_dir) for path in sorted(inspected)]
    data = DataProfile(downloaded=bool(paths), files=profiles, listed_files=listed_files)
    for path in paths:
        if path in inspected:
            continue
        size = path.stat().st_size
        if len(data.files) < MAX_LISTED_FILES:
            data.files.append(
                DataFileProfile(path=path.relative_to(data_dir).as_posix(), size_bytes=size)
            )
            continue
        data.omitted_files += 1
        data.omitted_bytes += size
        extension = path.suffix.lower() or "(none)"
        data.omitted_extensions[extension] = data.omitted_extensions.get(extension, 0) + 1
    data.files.sort(key=lambda profile: profile.path)

    submission = _find(profiles, "sample_submission") or _find(profiles, "gender_submission")
    if submission and submission.columns:
        data.sample_submission = submission.path
        data.submission_rows = None if submission.rows_estimated else submission.rows
        data.id_column = submission.columns[0].name
        data.target_columns = [column.name for column in submission.columns[1:]]
    else:
        train, test = _find(profiles, "train"), _find(profiles, "test")
        if train and test and train.columns and test.columns:
            test_names = {column.name for column in test.columns}
            data.target_columns = [
                column.name for column in train.columns if column.name not in test_names
            ]
    return data


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def render_schema_md(competition_title: str, data: DataProfile) -> str:
    lines = [f"# Data schema: {competition_title}", ""]
    if not data.downloaded:
        lines.extend(["Data has not been downloaded yet. Files listed on Kaggle:", ""])
        if data.listed_files:
            lines.extend(f"- `{name}`" for name in data.listed_files)
        else:
            lines.append("_No files listed._")
        return "\n".join(lines) + "\n"

    lines.append(
        f"Generated by kag from the first {SAMPLE_ROWS} rows of each CSV in `data/`. "
        "Types and missing counts describe that sample only."
    )
    if data.id_column or data.target_columns:
        lines.append("")
        if data.id_column:
            lines.append(f"- **ID column:** `{data.id_column}`")
        if data.target_columns:
            targets = ", ".join(f"`{name}`" for name in data.target_columns)
            lines.append(f"- **Target column(s):** {targets}")
        if data.sample_submission:
            lines.append(f"- **Submission template:** `data/{data.sample_submission}`")

    for profile in data.files:
        if profile.rows is None:
            rows = "rows not counted"
        elif profile.rows_estimated:
            rows = f"~{profile.rows:,} rows (estimated from line count)"
        else:
            rows = f"{profile.rows:,} rows"
        lines.extend(["", f"## `{profile.path}`", ""])
        lines.append(f"{_format_size(profile.size_bytes)}, {rows}")
        if not profile.inspected:
            lines.append("")
            lines.append("_Not inspected (only CSV files are profiled)._")
            continue
        lines.extend(["", "| Column | Type | Missing (sample) | Examples |", "|---|---|---|---|"])
        for column in profile.columns:
            examples = ", ".join(f"`{value[:30]}`" for value in column.examples)
            lines.append(
                f"| `{column.name}` | {column.type} | {column.missing_in_sample} | {examples} |"
            )
    if data.omitted_files:
        extensions = ", ".join(
            f"`{extension}` x{count:,}"
            for extension, count in sorted(
                data.omitted_extensions.items(), key=lambda item: (-item[1], item[0])
            )
        )
        lines.extend(
            [
                "",
                f"_...and {data.omitted_files:,} more files ({_format_size(data.omitted_bytes)}) "
                f"not listed: {extensions}._",
            ]
        )
    return "\n".join(lines) + "\n"


def build_manifest(
    competition: Competition,
    details: CompetitionDetails | None,
    data: DataProfile,
    notebook_path: str,
) -> dict:
    info = asdict(details) if details else {}
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kag_version": __version__,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "competition": {
            "slug": competition.slug,
            "title": info.get("title") or competition.title,
            "url": info.get("url") or f"https://www.kaggle.com/competitions/{competition.slug}",
            "description": info.get("description", ""),
            "category": info.get("category", ""),
            "reward": info.get("reward") or competition.reward,
            "deadline": info.get("deadline") or competition.deadline,
            "join_deadline": info.get("new_entrant_deadline", ""),
            "merger_deadline": info.get("merger_deadline", ""),
            "team_count": info.get("team_count") or competition.team_count,
            "evaluation_metric": info.get("evaluation_metric", ""),
            "max_daily_submissions": info.get("max_daily_submissions"),
            "max_team_size": info.get("max_team_size"),
            "notebook_only_submissions": info.get("is_kernels_submissions_only", False),
            "submissions_disabled": info.get("submissions_disabled", False),
            "tags": list(info.get("tags", ())),
        },
        "submission": {
            "template": f"data/{data.sample_submission}" if data.sample_submission else None,
            "id_column": data.id_column,
            "target_columns": data.target_columns,
            "rows": data.submission_rows,
        },
        "data": {
            "directory": "data",
            "downloaded": data.downloaded,
            "files": [
                {
                    "path": f"data/{profile.path}",
                    "size_bytes": profile.size_bytes,
                    "rows": profile.rows,
                    "rows_estimated": profile.rows_estimated,
                    "columns": [column.name for column in profile.columns],
                }
                for profile in data.files
            ],
            "omitted_files": {
                "count": data.omitted_files,
                "size_bytes": data.omitted_bytes,
                "extensions": data.omitted_extensions,
            },
            "listed_files": data.listed_files,
        },
        "paths": {
            "notebook": notebook_path,
            "notes": "notes.md",
            "schema": SCHEMA_PATH.as_posix(),
            "agents": "AGENTS.md",
        },
    }


def _submission_type(competition: dict) -> str:
    if competition["submissions_disabled"]:
        return "Disabled"
    if competition["notebook_only_submissions"]:
        return "Kaggle notebook only (code competition)"
    return "CSV file upload"


def render_agents_md(manifest: dict) -> str:
    competition = manifest["competition"]
    submission = manifest["submission"]
    slug = competition["slug"]
    lines = [
        f"# {competition['title']}",
        "",
        "Kaggle competition workspace created by [kag](https://github.com/Andrew-Girgis/kag).",
    ]
    if competition["description"]:
        lines.extend(["", competition["description"]])

    facts = [
        ("Competition", competition["url"]),
        ("Evaluation metric", competition["evaluation_metric"]),
        ("Deadline", competition["deadline"]),
        ("Join deadline", competition["join_deadline"]),
        ("Daily submission limit", competition["max_daily_submissions"]),
        ("Max team size", competition["max_team_size"]),
        ("Submission type", _submission_type(competition)),
    ]
    lines.extend(["", "## Competition", ""])
    lines.extend(f"- **{label}:** {value}" for label, value in facts if value)

    lines.extend(
        [
            "",
            "## Project layout",
            "",
            f"- `{manifest['paths']['notebook']}`: starter notebook",
            "- `notes.md`: overview, evaluation, data description, rules, and top notebooks",
            "- `data/`: competition data (gitignored); see `data/SCHEMA.md` for columns"
            if manifest["data"]["downloaded"]
            else f"- `data/`: not downloaded yet; run `kaggle competitions download -c {slug} -p data`",
            "- `.kag/competition.json`: machine-readable competition metadata",
        ]
    )

    lines.extend(["", "## Submission format", ""])
    if submission["template"]:
        columns = ", ".join(
            f"`{name}`" for name in [submission["id_column"], *submission["target_columns"]]
        )
        rows = f", {submission['rows']:,} rows" if submission["rows"] is not None else ""
        lines.append(f"Match `{submission['template']}`: columns {columns}{rows}.")
    else:
        lines.append("See the Evaluation section of `notes.md`.")

    lines.extend(
        [
            "",
            "## Working rules",
            "",
            "- Read the Rules section of `notes.md` before using external data or pretrained "
            "models.",
            "- Treat files in `data/` as read-only; write derived data and models elsewhere.",
        ]
    )
    if competition["submissions_disabled"]:
        lines.append(
            "- Submissions are disabled for this competition; Kaggle will not accept new "
            "submissions."
        )
    else:
        submit = (
            "Submit by running a Kaggle notebook attached to the competition."
            if competition["notebook_only_submissions"]
            else f'Submit with `kaggle competitions submit -c {slug} -f <file> -m "<message>"`.'
        )
        lines.extend(
            [
                "- Check a submission's columns and row count against the template before "
                "submitting; daily submissions are limited.",
                f"- {submit}",
            ]
        )
    return "\n".join(lines) + "\n"


def manifest_json(manifest: dict) -> str:
    return json.dumps(manifest, indent=2) + "\n"
