from __future__ import annotations

import contextlib
import io
import threading
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")

_API_LOCK = threading.RLock()
_api: Any | None = None


class KaggleSdkError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompetitionDetails:
    slug: str
    title: str
    description: str = ""
    category: str = ""
    reward: str = ""
    deadline: str = ""
    new_entrant_deadline: str = ""
    merger_deadline: str = ""
    team_count: int = 0
    user_has_entered: bool = False
    evaluation_metric: str = ""
    max_daily_submissions: int | None = None
    max_team_size: int | None = None
    is_kernels_submissions_only: bool = False
    submissions_disabled: bool = False
    url: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ListedCompetition:
    slug: str
    title: str
    deadline: str
    reward: str
    team_count: int
    user_has_entered: bool


@contextlib.contextmanager
def _quiet() -> Generator[None, None, None]:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


def _load_api() -> Any:
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    return api


def _get_api() -> Any:
    global _api
    with _API_LOCK:
        if _api is None:
            try:
                with _quiet():
                    _api = _load_api()
            except (Exception, SystemExit) as exc:
                raise KaggleSdkError(f"Kaggle library unavailable: {exc or type(exc).__name__}")
        return _api


def _call(operation: Callable[[Any], T]) -> T:
    with _API_LOCK:
        api = _get_api()
        try:
            with _quiet():
                return operation(api)
        except (Exception, SystemExit) as exc:
            raise KaggleSdkError(str(exc) or type(exc).__name__) from None


def reset() -> None:
    global _api
    with _API_LOCK:
        _api = None


def sdk_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("kaggle")
    except Exception:
        return None


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _slug(ref: object) -> str:
    return _text(ref).rstrip("/").rsplit("/", 1)[-1]


def _optional_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def list_competitions(
    group: str = "general",
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
) -> tuple[list[ListedCompetition], bool]:
    response = _call(
        lambda api: api.competitions_list(
            group=group, page=page, page_size=page_size, search=search or None
        )
    )
    competitions = [
        ListedCompetition(
            slug=_slug(item.ref),
            title=_text(item.title) or _slug(item.ref),
            deadline=_text(item.deadline),
            reward=_text(item.reward),
            team_count=_optional_int(item.team_count) or 0,
            user_has_entered=bool(item.user_has_entered),
        )
        for item in (getattr(response, "competitions", None) or [])
        if _slug(item.ref)
    ]
    has_more = bool(getattr(response, "next_page_token", None)) or len(competitions) >= page_size
    return competitions, has_more


def get_competition_details(slug: str) -> CompetitionDetails:
    def fetch(api: Any) -> Any:
        from kagglesdk.competitions.types.competition_api_service import (
            ApiGetCompetitionRequest,
        )

        request = ApiGetCompetitionRequest()
        request.competition_name = slug
        with api.build_kaggle_client() as client:
            return client.competitions.competition_api_client.get_competition(request)

    item = _call(fetch)
    tags = tuple(
        _text(getattr(tag, "name", "")) for tag in (item.tags or []) if getattr(tag, "name", "")
    )
    return CompetitionDetails(
        slug=_slug(item.ref) or slug,
        title=_text(item.title) or slug,
        description=_text(item.description),
        category=_text(item.category),
        reward=_text(item.reward),
        deadline=_text(item.deadline),
        new_entrant_deadline=_text(item.new_entrant_deadline),
        merger_deadline=_text(item.merger_deadline),
        team_count=_optional_int(item.team_count) or 0,
        user_has_entered=bool(item.user_has_entered),
        evaluation_metric=_text(item.evaluation_metric),
        max_daily_submissions=_optional_int(item.max_daily_submissions),
        max_team_size=_optional_int(item.max_team_size),
        is_kernels_submissions_only=bool(item.is_kernels_submissions_only),
        submissions_disabled=bool(item.submissions_disabled),
        url=_text(item.url),
        tags=tags,
    )


@dataclass(frozen=True)
class CompetitionPage:
    name: str
    content: str
    title: str = ""


@dataclass(frozen=True)
class NotebookSummary:
    title: str
    author: str
    ref: str
    votes: int


def list_competition_pages(slug: str) -> list[CompetitionPage]:
    pages = _call(lambda api: api.competition_list_pages(slug))
    return [
        CompetitionPage(
            name=_text(page.name),
            content=page.content or "",
            title=_text(getattr(page, "post_title", "")),
        )
        for page in (pages or [])
        if _text(page.name)
    ]


def list_top_notebooks(slug: str, limit: int = 20) -> list[NotebookSummary]:
    kernels = _call(
        lambda api: api.kernels_list(competition=slug, sort_by="voteCount", page_size=limit)
    )
    return [
        NotebookSummary(
            title=_text(kernel.title) or "Untitled",
            author=_text(kernel.author) or "Unknown",
            ref=_text(kernel.ref),
            votes=_optional_int(kernel.total_votes) or 0,
        )
        for kernel in (kernels or [])
        if _text(kernel.ref)
    ]
