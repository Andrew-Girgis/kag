from __future__ import annotations

import re
import threading

from . import kaggle_sdk
from .kaggle_sdk import CompetitionPage, NotebookSummary

BASE_WEB_URL = "https://www.kaggle.com"
SECTION_HEADING_LEVEL = 4
HTML_TAG_PATTERN = re.compile(
    r"<(p|div|h[1-6]|ul|ol|li|br|b|strong|em|i|a|table|img|span|code|pre)\b", re.IGNORECASE
)
HEADING_PATTERN = re.compile(r"^(#{1,6})(\s+.*)$")
FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")
FENCED_BLOCK_PATTERN = re.compile(r"^\s*(```|~~~).*?^\s*\1[^\n]*$", re.MULTILINE | re.DOTALL)
SETEXT_UNDERLINE_PATTERN = re.compile(r"^\s{0,3}(=+|-+)\s*$")


def _html_to_markdown(html: str, base_url: str) -> str:
    from urllib.parse import urljoin

    from bs4 import BeautifulSoup
    from markdownify import markdownify

    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select("a[href]"):
        anchor["href"] = urljoin(base_url, anchor["href"])
    for image in soup.select("img[src]"):
        image["src"] = urljoin(base_url, image["src"])
    markdown = markdownify(str(soup), heading_style="ATX", bullets="-")
    markdown = "\n".join(line.rstrip() for line in markdown.splitlines())
    markdown = markdown.replace("\\*\\*", "**")
    markdown = markdown.replace("\\*", "*")
    markdown = markdown.replace("\\_", "_")
    markdown = re.sub(r"^(#{1,6})([^ #])", r"\1 \2", markdown, flags=re.MULTILINE)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip()


def _is_html(content: str) -> bool:
    return bool(HTML_TAG_PATTERN.search(FENCED_BLOCK_PATTERN.sub("", content)))


def _setext_to_atx(markdown: str) -> str:
    lines = markdown.splitlines()
    converted: list[str] = []
    in_fence = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            converted.append(line)
            index += 1
            continue
        following = lines[index + 1] if index + 1 < len(lines) else ""
        underline = SETEXT_UNDERLINE_PATTERN.match(following)
        is_text = (
            line.strip()
            and not in_fence
            and not HEADING_PATTERN.match(line)
            and not line.lstrip().startswith(("-", "*", "+", ">", "|"))
        )
        if underline and is_text and not FENCE_PATTERN.match(following):
            level = "#" if underline.group(1).startswith("=") else "##"
            converted.append(f"{level} {line.strip()}")
            index += 2
            continue
        converted.append(line)
        index += 1
    return "\n".join(converted)


def _page_markdown(content: str, slug: str) -> str:
    base_url = f"{BASE_WEB_URL}/competitions/{slug}/overview"
    if _is_html(content):
        return _html_to_markdown(content, base_url)
    return re.sub(r"\n{3,}", "\n\n", content.replace("\r\n", "\n")).strip()


def _demote_headings(markdown: str, minimum_level: int = SECTION_HEADING_LEVEL) -> str:
    lines = _setext_to_atx(markdown).splitlines()
    in_fence = False
    levels: list[int] = []
    for line in lines:
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            continue
        match = HEADING_PATTERN.match(line)
        if match and not in_fence:
            levels.append(len(match.group(1)))
    if not levels:
        return "\n".join(lines)
    shift = max(0, minimum_level - min(levels))
    if shift == 0:
        return "\n".join(lines)

    demoted: list[str] = []
    in_fence = False
    for line in lines:
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            demoted.append(line)
            continue
        match = HEADING_PATTERN.match(line)
        if match and not in_fence:
            level = min(6, len(match.group(1)) + shift)
            demoted.append("#" * level + match.group(2))
        else:
            demoted.append(line)
    return "\n".join(demoted)


def _page_title(name: str) -> str:
    if " " in name or name != name.lower():
        return name.strip()
    return name.replace("-", " ").replace("_", " ").strip().title()


def _section_for(name: str) -> str:
    lowered = name.lower()
    if "rule" in lowered:
        return "Rules"
    if "evaluation" in lowered:
        return "Evaluation"
    if "data" in lowered:
        return "Data"
    return "Overview"


def _overview_priority(page: CompetitionPage) -> int:
    lowered = page.name.lower()
    return 0 if ("description" in lowered or "abstract" in lowered) else 1


def _build_code_section(notebooks: list[NotebookSummary]) -> str:
    if not notebooks:
        return "_No public notebooks yet._"
    lines = ["Most-voted notebooks for this competition:", ""]
    for notebook in notebooks:
        url = f"{BASE_WEB_URL}/code/{notebook.ref}"
        lines.append(f"- [{notebook.title}]({url}) - {notebook.author} (votes: {notebook.votes})")
    return "\n".join(lines)


def fetch_competition_markdown_sections(
    slug: str,
    cancel: threading.Event | None = None,
) -> tuple[dict[str, str], list[str]]:
    sections: dict[str, str] = {}
    warnings: list[str] = []

    def cancelled() -> bool:
        return cancel is not None and cancel.is_set()

    if cancelled():
        return sections, warnings
    try:
        pages = kaggle_sdk.list_competition_pages(slug)
    except kaggle_sdk.KaggleSdkError as exc:
        warnings.append(f"Could not fetch competition pages: {exc}")
        pages = []

    parts: dict[str, list[str]] = {}
    ordered_pages = sorted(pages, key=_overview_priority)
    for page in ordered_pages:
        content = _page_markdown(page.content, slug)
        if not content:
            continue
        chunk = f"### {page.title or _page_title(page.name)}\n\n{_demote_headings(content)}"
        parts.setdefault(_section_for(page.name), []).append(chunk)
    for name, chunks in parts.items():
        sections[name] = "\n\n".join(chunks).strip()

    if cancelled():
        return sections, warnings
    try:
        notebooks = kaggle_sdk.list_top_notebooks(slug)
    except kaggle_sdk.KaggleSdkError as exc:
        warnings.append(f"Could not fetch competition notebooks: {exc}")
    else:
        sections["Code"] = _build_code_section(notebooks)

    return sections, warnings
