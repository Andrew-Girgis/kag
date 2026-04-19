import csv
import io
import subprocess
import time
import webbrowser
from dataclasses import dataclass


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
            return [], False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return [], False

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
    base = f"https://www.kaggle.com/competitions/{slug}"
    webbrowser.open_new_tab(f"{base}/overview")
    webbrowser.open_new_tab(f"{base}/rules")


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
