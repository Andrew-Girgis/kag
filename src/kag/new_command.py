from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

from . import context
from .config import Config
from .kaggle_api import Competition, _extract_slug, check_competition_access
from .kaggle_sdk import CompetitionDetails
from .project import (
    ProjectCreationCancelled,
    ProjectCreationError,
    create_project,
    existing_project_dir,
    fetch_competition_details,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NEEDS_JOIN = 3
EXIT_EXISTS = 4
EXIT_CANCELLED = 130

NEW_USAGE = "kag new <competition> [--no-download] [--no-git] [--no-venv] [--editor NAME] [--force] [--json]"
SKIPPED_DIRECTORIES = {".git", ".venv", "data"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kag new",
        usage=NEW_USAGE,
        description="Create a Kaggle competition workspace without the TUI.",
    )
    parser.add_argument("competition", help="Competition slug or URL, e.g. titanic.")
    parser.add_argument("--no-download", action="store_true", help="Skip downloading data.")
    parser.add_argument("--no-git", action="store_true", help="Skip git init and commit.")
    parser.add_argument("--no-venv", action="store_true", help="Skip creating .venv.")
    parser.add_argument("--editor", help="Open the project in this editor afterwards.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Add missing files to an existing project (never overwrites).",
    )
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    return parser


def _needs_join(details: str) -> bool:
    lowered = details.lower()
    return any(marker in lowered for marker in ("403", "forbidden", "rules", "join"))


def _project_files(project_dir: Path) -> set[Path]:
    files: set[Path] = set()
    for path in project_dir.rglob("*"):
        relative = path.relative_to(project_dir)
        if relative.parts[0] in SKIPPED_DIRECTORIES and relative != context.SCHEMA_PATH:
            continue
        if path.is_file():
            files.add(relative)
    return files


def _data_file_count(project_dir: Path) -> int:
    data_dir = project_dir / "data"
    if not data_dir.is_dir():
        return 0
    return sum(
        1
        for path in data_dir.rglob("*")
        if path.is_file() and path.name != context.SCHEMA_PATH.name
    )


def _competition(slug: str, details: CompetitionDetails | None) -> Competition:
    if details is None:
        return Competition(slug=slug, title=slug, deadline="", reward="", team_count="0")
    return Competition(
        slug=slug,
        title=details.title,
        deadline=details.deadline,
        reward=details.reward,
        team_count=str(details.team_count),
        is_joined=details.user_has_entered,
    )


def _resolve_editor(config: Config, requested: str | None) -> tuple[str | None, str | None]:
    if not requested:
        return None, None
    for editor in config.available_editors():
        if requested in (editor["key"], editor["cmd"]):
            return editor["cmd"], None
    available = ", ".join(editor["key"] for editor in config.available_editors()) or "none"
    return None, f"Editor '{requested}' is not installed. Available: {available}"


def _emit(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2))
        return
    print(f"{result['status']}: {result.get('message', '')}".rstrip(": "))
    if result.get("path"):
        print(f"path: {result['path']}")
    if result.get("url"):
        print(f"url: {result['url']}")
    for step in result.get("next_steps", []):
        print(f"next: {step}")
    for warning in result.get("warnings", []):
        print(f"warning: {warning}")


def run_new(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    slug = _extract_slug(args.competition.strip())
    as_json = args.json
    config = Config.load()
    if args.no_git:
        config.auto_git = False
    if args.no_venv:
        config.auto_venv = False
    project_dir = config.kag_path / slug
    base: dict = {"slug": slug, "path": str(project_dir)}

    def finish(result: dict, code: int) -> int:
        _emit({**base, **result}, as_json)
        return code

    if not slug or slug in {".", ".."} or "/" in slug:
        return finish(
            {"status": "error", "message": f"Invalid competition: {args.competition}"},
            EXIT_ERROR,
        )

    editor, editor_error = _resolve_editor(config, args.editor)
    if editor_error:
        return finish({"status": "error", "message": editor_error}, EXIT_ERROR)

    existed = existing_project_dir(config, slug) is not None
    if existed and not args.force:
        return finish(
            {
                "status": "exists",
                "message": "Project folder already exists; pass --force to add missing files.",
                "next_steps": [f"cd {project_dir}", "Read AGENTS.md"],
            },
            EXIT_EXISTS,
        )

    def progress(message: str) -> None:
        print(message, file=sys.stderr)

    progress("Fetching competition details...")
    details = fetch_competition_details(slug)
    warnings: list[str] = []
    if details is None:
        warnings.append("Competition details unavailable from the Kaggle library.")
    else:
        base["title"] = details.title

    rules_url = f"https://www.kaggle.com/competitions/{slug}/rules"
    download = not args.no_download
    if download:
        progress("Checking access...")
        access_ok, access_details = check_competition_access(slug)
        if not access_ok:
            if _needs_join(access_details):
                return finish(
                    {
                        "status": "needs_join",
                        "url": rules_url,
                        "message": "Join the competition and accept its rules on Kaggle, "
                        f"then run this command again. Kaggle said: {access_details}",
                    },
                    EXIT_NEEDS_JOIN,
                )
            return finish({"status": "error", "message": access_details}, EXIT_ERROR)

    before = _project_files(project_dir) if existed else set()
    data_before = _data_file_count(project_dir)
    cancel = threading.Event()
    outcome: dict[str, BaseException] = {}
    done = threading.Event()

    def work() -> None:
        try:
            create_project(
                competition=_competition(slug, details),
                config=config,
                download_files=download,
                editor=editor,
                progress=progress,
                cancel=cancel,
                details=details,
            )
        except BaseException as exc:
            outcome["error"] = exc
        finally:
            done.set()

    threading.Thread(target=work, name="kag-new", daemon=True).start()
    try:
        while not done.wait(0.2):
            pass
    except KeyboardInterrupt:
        cancel.set()
        progress("Cancelling...")
        while not done.wait(0.2):
            pass

    error = outcome.get("error")
    if isinstance(error, ProjectCreationCancelled):
        return finish(
            {
                "status": "cancelled",
                "message": "Project setup cancelled; changes were rolled back.",
            },
            EXIT_CANCELLED,
        )
    if isinstance(error, ProjectCreationError):
        message = str(error)
        if _needs_join(message):
            return finish(
                {"status": "needs_join", "url": rules_url, "message": message},
                EXIT_NEEDS_JOIN,
            )
        return finish({"status": "error", "message": message}, EXIT_ERROR)
    if error is not None:
        return finish(
            {"status": "error", "message": f"Project creation failed: {error}"}, EXIT_ERROR
        )

    added = sorted(path.as_posix() for path in _project_files(project_dir) - before)
    notebook = f"{slug}.ipynb"
    files = {
        "agents": "AGENTS.md",
        "notes": "notes.md",
        "notebook": notebook,
        "manifest": context.MANIFEST_PATH.as_posix(),
        "schema": context.SCHEMA_PATH.as_posix()
        if (project_dir / context.SCHEMA_PATH).exists()
        else None,
    }
    return finish(
        {
            "status": "updated" if existed else "created",
            "message": "Workspace ready.",
            "files": files,
            "added": added,
            "data_files_added": _data_file_count(project_dir) - data_before,
            "warnings": warnings,
            "next_steps": [f"cd {project_dir}", "Read AGENTS.md"],
        },
        EXIT_OK,
    )
