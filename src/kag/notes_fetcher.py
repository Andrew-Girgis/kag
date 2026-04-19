from __future__ import annotations

import re
from urllib.parse import urljoin


BASE_WEB_URL = "https://www.kaggle.com"
BASE_API_URL = "https://www.kaggle.com/api/i"


def _html_to_markdown(html: str, base_url: str) -> str:
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


def _competition_session(slug: str):
    import requests

    session = requests.Session()
    overview_url = f"{BASE_WEB_URL}/competitions/{slug}/overview"
    session.get(overview_url, timeout=20)
    xsrf_token = session.cookies.get("XSRF-TOKEN") or session.cookies.get("CSRF-TOKEN")
    headers = {
        "content-type": "application/json",
        "x-requested-with": "XMLHttpRequest",
        "origin": BASE_WEB_URL,
        "referer": overview_url,
    }
    if xsrf_token:
        headers["x-xsrf-token"] = xsrf_token
    return session, headers


def _post_api(session, headers: dict[str, str], endpoint: str, payload: dict):
    response = session.post(
        f"{BASE_API_URL}/{endpoint}",
        json=payload,
        headers=headers,
        timeout=25,
    )
    if response.status_code != 200:
        return None
    return response.json()


def _build_code_section(kernels: list[dict]) -> str:
    if not kernels:
        return "_No code entries returned by Kaggle API._"

    lines = [
        "Top notebooks from competition code tab:",
        "",
    ]
    for kernel in kernels[:20]:
        title = kernel.get("title") or "Untitled"
        author = (kernel.get("author") or {}).get("displayName") or "Unknown"
        votes = kernel.get("totalVotes", 0)
        views = kernel.get("totalViews", 0)
        script_url = kernel.get("scriptUrl") or ""
        full_url = urljoin(BASE_WEB_URL, script_url)
        lines.append(f"- [{title}]({full_url}) - {author} (votes: {votes}, views: {views})")
    return "\n".join(lines)


def _format_evaluation_algorithm(value) -> str:
    if isinstance(value, dict):
        name = value.get("name")
        if name:
            return str(name)
        description = value.get("description")
        if description:
            return str(description)
        return str(value)
    if isinstance(value, list):
        formatted = [_format_evaluation_algorithm(item) for item in value]
        formatted = [item for item in formatted if item]
        return ", ".join(formatted)
    if value is None:
        return ""
    return str(value)


def fetch_competition_markdown_sections(slug: str) -> tuple[dict[str, str], list[str]]:
    sections: dict[str, str] = {}
    warnings: list[str] = []

    try:
        session, headers = _competition_session(slug)
    except Exception as exc:
        warnings.append(f"Failed to create Kaggle web session: {exc}")
        return sections, warnings

    competition = _post_api(
        session,
        headers,
        "competitions.CompetitionService/GetCompetition",
        {"competitionName": slug},
    )
    if not competition:
        warnings.append("Could not fetch competition overview metadata")
        return sections, warnings

    competition_id = competition.get("id")
    if not competition_id:
        warnings.append("Competition ID missing from Kaggle API response")
        return sections, warnings

    pages_response = _post_api(
        session,
        headers,
        "competitions.PageService/ListPages",
        {"competitionId": competition_id},
    )

    page_items = (pages_response or {}).get("pages", [])

    overview_parts: list[str] = []
    evaluation_parts: list[str] = []
    data_parts: list[str] = []
    rules_parts: list[str] = []

    brief = competition.get("briefDescription") or ""
    if brief:
        overview_parts.append(brief.strip())

    evaluation_algo = _format_evaluation_algorithm(competition.get("evaluationAlgorithm"))
    if evaluation_algo:
        evaluation_parts.extend([
            "### Evaluation Algorithm",
            "",
            str(evaluation_algo).strip(),
        ])

    for page in page_items:
        name = str(page.get("name") or "").strip()
        title = str(page.get("postTitle") or name or "Page").strip().title()
        content_html = page.get("content") or ""
        if not content_html:
            continue
        page_url = f"{BASE_WEB_URL}/competitions/{slug}/overview"
        content_md = _html_to_markdown(content_html, page_url)
        if not content_md:
            continue

        chunk = f"### {title}\n\n{content_md}"
        lowered_name = name.lower()
        if "rule" in lowered_name:
            rules_parts.append(chunk)
        elif "evaluation" in lowered_name:
            evaluation_parts.append(chunk)
        elif "data" in lowered_name:
            data_parts.append(chunk)
        else:
            overview_parts.append(chunk)

    kernels_payload = {
        "kernelFilterCriteria": {
            "search": "",
            "listRequest": {
                "competitionId": competition_id,
                "sortBy": "HOTNESS",
                "pageSize": 20,
                "group": "EVERYONE",
                "page": 1,
                "modelIds": [],
                "modelInstanceIds": [],
                "excludeKernelIds": [],
                "tagIds": "",
                "excludeResultsFilesOutputs": False,
                "wantOutputFiles": False,
                "excludeNonAccessedDatasources": True,
            },
        },
        "detailFilterCriteria": {
            "deletedAccessBehavior": "RETURN_NOTHING",
            "unauthorizedAccessBehavior": "RETURN_NOTHING",
            "excludeResultsFilesOutputs": False,
            "wantOutputFiles": False,
            "kernelIds": [],
            "outputFileTypes": [],
            "includeInvalidDataSources": False,
        },
        "readMask": "pinnedKernels",
    }
    kernels_response = _post_api(
        session,
        headers,
        "kernels.KernelsService/ListKernels",
        kernels_payload,
    )
    kernels = (kernels_response or {}).get("kernels", [])

    if overview_parts:
        sections["Overview"] = "\n\n".join(overview_parts).strip()
    if evaluation_parts:
        sections["Evaluation"] = "\n\n".join(evaluation_parts).strip()
    if data_parts:
        sections["Data"] = "\n\n".join(data_parts).strip()
    if rules_parts:
        sections["Rules"] = "\n\n".join(rules_parts).strip()
    if kernels_response is None:
        warnings.append("Could not fetch competition code listing")
    else:
        sections["Code"] = _build_code_section(kernels)

    return sections, warnings
