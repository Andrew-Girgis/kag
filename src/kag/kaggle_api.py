import csv
import io
import subprocess
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path


class KaggleFetchError(RuntimeError):
    pass


def _extract_slug(ref: str) -> str:
    if ref.startswith("http"):
        return ref.rstrip("/").split("/")[-1]
    return ref


def _humanize_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


@dataclass
class Competition:
    slug: str
    title: str
    deadline: str
    reward: str
    team_count: str
    has_data: bool = False
    is_joined: bool = False

    @property
    def display_title(self) -> str:
        if self.title == self.slug or not self.title:
            return _humanize_slug(self.slug)[:60]
        return self.title[:60]

    @property
    def safe_id(self) -> str:
        slug = self.slug
        return "".join(c if c.isalnum() or c in "-_" else "-" for c in slug)


@dataclass
class LocalProject:
    name: str
    path: str
    modified_days_ago: float

    @property
    def display_title(self) -> str:
        return self.name[:60]


@dataclass(frozen=True)
class DownloadResult:
    success: bool
    details: str
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompetitionFile:
    name: str
    size: int | None = None

    @property
    def display_size(self) -> str:
        if self.size is None:
            return "unknown size"
        size = float(self.size)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"


@dataclass(frozen=True)
class FileListResult:
    success: bool
    files: tuple[CompetitionFile, ...] = ()
    details: str = ""


def _first_detail_line(stdout: str, stderr: str) -> str:
    details = (stderr or stdout or "").strip()
    if details:
        return details.splitlines()[0]
    return ""


def _csv_payload(text: str, expected_header: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(expected_header):
            return "\n".join(lines[index:])
    return text


def list_competitions_page(
    group: str = "general",
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Competition], bool]:
    cmd = [
        "kaggle",
        "competitions",
        "list",
        "--csv",
        "--page-size",
        str(page_size),
        "--page",
        str(page),
    ]
    if group:
        cmd.extend(["--group", group])
    if search:
        cmd.extend(["-s", search])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            if details:
                details = details.splitlines()[0]
            raise KaggleFetchError(details or "Kaggle competitions could not be loaded")
    except FileNotFoundError as exc:
        raise KaggleFetchError("kaggle CLI not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise KaggleFetchError("Kaggle competitions request timed out") from exc

    competitions = []
    reader = csv.DictReader(io.StringIO(result.stdout))
    if reader.fieldnames is None:
        raise KaggleFetchError("Kaggle competitions response was not valid CSV")
    if "ref" not in reader.fieldnames:
        raise KaggleFetchError("Kaggle competitions response was not valid CSV")
    for row in reader:
        ref = row.get("ref", "").strip()
        if not ref:
            continue
        slug = _extract_slug(ref)
        competitions.append(
            Competition(
                slug=slug,
                title=row.get("title", slug).strip(),
                deadline=row.get("deadline", "").strip(),
                reward=row.get("reward", "").strip(),
                team_count=row.get("teamsCount", "0").strip(),
            )
        )
    has_more = len(competitions) >= page_size
    return competitions, has_more


def list_competitions(
    group: str = "general",
    search: str | None = None,
    page: int = 1,
    page_size: int = 200,
) -> list[Competition]:
    competitions, _ = list_competitions_page(
        group=group,
        search=search,
        page=page,
        page_size=page_size,
    )
    return competitions


def list_entered_competitions() -> list[Competition]:
    return list_competitions(group="entered")


def list_competition_files(slug: str) -> FileListResult:
    cmd = ["kaggle", "competitions", "files", "-v", slug]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            details = _first_detail_line(result.stdout, result.stderr)
            return FileListResult(False, details=details or "Competition files could not be listed")
    except subprocess.TimeoutExpired:
        return FileListResult(False, details="Kaggle files request timed out")
    except FileNotFoundError:
        return FileListResult(False, details="kaggle CLI not found")

    files = []
    reader = csv.DictReader(io.StringIO(_csv_payload(result.stdout, "name,")))
    if reader.fieldnames is None or "name" not in reader.fieldnames:
        return FileListResult(False, details="Kaggle files response was not valid CSV")
    for row in reader:
        name = row.get("name", "").strip()
        if name:
            size_text = row.get("size", "").strip()
            size = int(size_text) if size_text.isdigit() else None
            files.append(CompetitionFile(name=name, size=size))
    return FileListResult(True, tuple(files))


def get_competition_files(slug: str) -> list[str]:
    result = list_competition_files(slug)
    if result.success:
        return [file.name for file in result.files]
    return []


def download_competition(slug: str, path: str) -> DownloadResult:
    cmd = ["kaggle", "competitions", "download", "-q", slug, "-p", path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return DownloadResult(False, "Kaggle download timed out")
    except FileNotFoundError:
        return DownloadResult(False, "kaggle CLI not found")

    if result.returncode != 0:
        details = _first_detail_line(result.stdout, result.stderr)
        return DownloadResult(False, details or "Kaggle download failed")

    downloaded_files = tuple(sorted(p.name for p in Path(path).iterdir() if p.is_file()))
    if not downloaded_files:
        return DownloadResult(False, "Kaggle download completed but no files were found")

    return DownloadResult(True, "Download completed", downloaded_files)


def check_competition_access(slug: str) -> tuple[bool, str]:
    cmd = ["kaggle", "competitions", "files", "-v", slug]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, "Unable to run kaggle access check"

    if result.returncode == 0:
        return True, "Access confirmed"

    details = (result.stderr or result.stdout or "").strip()
    if details:
        details = details.splitlines()[0]
    return False, details or "Competition access denied"


def open_competition_in_browser(slug: str) -> None:
    open_competition_page(slug, "overview")
    open_competition_page(slug, "rules")


def open_competition_page(slug: str, page: str) -> None:
    base = f"https://www.kaggle.com/competitions/{slug}"
    webbrowser.open_new_tab(f"{base}/{page}")


def ensure_competition_access(
    slug: str,
    retries: int = 6,
    wait_seconds: int = 4,
) -> tuple[bool, str]:
    access_ok, details = check_competition_access(slug)
    if access_ok:
        return True, details

    open_competition_in_browser(slug)
    for _ in range(retries):
        time.sleep(wait_seconds)
        access_ok, details = check_competition_access(slug)
        if access_ok:
            return True, "Access confirmed after browser join"

    return False, details


def get_competition_description(slug: str) -> str:
    cmd = ["kaggle", "competitions", "list", "--csv", "-s", slug]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""

    reader = csv.DictReader(io.StringIO(result.stdout))
    for row in reader:
        if row.get("ref", "").strip() == slug:
            desc = row.get("description", "").strip()
            if desc:
                return desc
    return ""
