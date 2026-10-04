from __future__ import annotations

import threading

import pytest

from kag import kaggle_sdk, notes_fetcher
from kag.kaggle_sdk import CompetitionPage, NotebookSummary

TITANIC_PAGES = [
    CompetitionPage("rules", "### One account per participant\n\nNo multiple accounts."),
    CompetitionPage(
        "Frequently Asked Questions", "<h2>What is a Getting Started competition?</h2>"
    ),
    CompetitionPage(
        "Description", "## Ahoy, welcome to Kaggle!\n\nPredict survival.\n\n### The Challenge"
    ),
    CompetitionPage(
        "Evaluation", "<h2>Goal</h2>\n<p>Predict <b>0 or 1</b> for each passenger.</p>"
    ),
    CompetitionPage(
        "data-description", "<h3>Overview</h3>\n<p>Two groups: train.csv and test.csv</p>"
    ),
    CompetitionPage("empty", ""),
]


@pytest.fixture
def fake_sdk(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def pages(slug: str) -> list[CompetitionPage]:
        calls.append("pages")
        return TITANIC_PAGES

    def notebooks(slug: str, limit: int = 20) -> list[NotebookSummary]:
        calls.append("notebooks")
        return [
            NotebookSummary(
                "Titanic Tutorial", "Alexis Cook", "alexisbcook/titanic-tutorial", 61298
            )
        ]

    monkeypatch.setattr(kaggle_sdk, "list_competition_pages", pages)
    monkeypatch.setattr(kaggle_sdk, "list_top_notebooks", notebooks)
    return calls


def test_pages_are_grouped_into_sections(fake_sdk: list[str]) -> None:
    sections, warnings = notes_fetcher.fetch_competition_markdown_sections("titanic")

    assert warnings == []
    assert set(sections) == {"Overview", "Evaluation", "Data", "Rules", "Code"}
    overview = sections["Overview"]
    assert overview.index("### Description") < overview.index("### Frequently Asked Questions")
    assert "#### Ahoy, welcome to Kaggle!" in overview
    assert "##### The Challenge" in overview
    assert "#### What is a Getting Started competition?" in overview
    assert sections["Evaluation"].startswith("### Evaluation\n\n#### Goal")
    assert "**0 or 1**" in sections["Evaluation"]
    assert sections["Data"].startswith("### Data Description\n\n#### Overview")
    assert sections["Rules"].startswith("### Rules\n\n#### One account per participant")


def test_page_headings_never_reach_section_level(fake_sdk: list[str]) -> None:
    sections, _ = notes_fetcher.fetch_competition_markdown_sections("titanic")

    for content in sections.values():
        for line in content.splitlines():
            assert not line.startswith("## "), line


def test_code_section_links_to_most_voted_notebooks(fake_sdk: list[str]) -> None:
    sections, _ = notes_fetcher.fetch_competition_markdown_sections("titanic")

    assert (
        "- [Titanic Tutorial](https://www.kaggle.com/code/alexisbcook/titanic-tutorial)"
        " - Alexis Cook (votes: 61298)"
    ) in sections["Code"]


def test_sdk_failures_become_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    sections, warnings = notes_fetcher.fetch_competition_markdown_sections("titanic")

    assert sections == {}
    assert len(warnings) == 2
    assert warnings[0].startswith("Could not fetch competition pages:")
    assert warnings[1].startswith("Could not fetch competition notebooks:")


def test_fetch_does_not_start_when_already_cancelled(fake_sdk: list[str]) -> None:
    cancel = threading.Event()
    cancel.set()

    assert notes_fetcher.fetch_competition_markdown_sections("titanic", cancel=cancel) == ({}, [])
    assert fake_sdk == []


def test_fetch_skips_notebooks_when_cancelled_after_pages(
    fake_sdk: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancel = threading.Event()

    def pages_then_cancel(slug: str) -> list[CompetitionPage]:
        fake_sdk.append("pages")
        cancel.set()
        return TITANIC_PAGES[:1]

    monkeypatch.setattr(kaggle_sdk, "list_competition_pages", pages_then_cancel)

    sections, _ = notes_fetcher.fetch_competition_markdown_sections("titanic", cancel=cancel)

    assert fake_sdk == ["pages"]
    assert "Code" not in sections


def test_demote_headings_leaves_code_fences_alone() -> None:
    markdown = "# Title\n\n```python\n# not a heading\n```\n\n## Sub"

    assert notes_fetcher._demote_headings(markdown) == (
        "#### Title\n\n```python\n# not a heading\n```\n\n##### Sub"
    )
