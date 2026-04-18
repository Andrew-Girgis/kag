import csv
import io
import subprocess
from dataclasses import dataclass

from rich.console import Console


def _extract_slug(ref: str) -> str:
    if ref.startswith("http"):
        return ref.rstrip("/").split("/")[-1]
    return ref


@dataclass
class Competition:
    slug: str
    title: str
    deadline: str
    reward: str
    team_count: str
    has_data: bool = False

    @property
    def display_title(self) -> str:
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


def list_competitions(group: str = "general", search: str | None = None) -> list[Competition]:
    cmd = ["kaggle", "competitions", "list", "--csv", "--page-size", "200"]
    if group:
        cmd.extend(["--group", group])
    if search:
        cmd.extend(["-s", search])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    competitions = []
    reader = csv.DictReader(io.StringIO(result.stdout))
    for row in reader:
        ref = row.get("ref", "").strip()
        if not ref:
            continue
        slug = _extract_slug(ref)
        competitions.append(Competition(
            slug=slug,
            title=row.get("title", slug).strip(),
            deadline=row.get("deadline", "").strip(),
            reward=row.get("reward", "").strip(),
            team_count=row.get("teamsCount", "0").strip(),
        ))
    return competitions


def list_entered_competitions() -> list[Competition]:
    return list_competitions(group="entered")


def get_competition_files(slug: str) -> list[str]:
    cmd = ["kaggle", "competitions", "files", "-v", slug]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    files = []
    reader = csv.DictReader(io.StringIO(result.stdout))
    for row in reader:
        name = row.get("name", "").strip()
        if name:
            files.append(name)
    return files


def download_competition(slug: str, path: str) -> bool:
    cmd = ["kaggle", "competitions", "download", "-q", slug, "-p", path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


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