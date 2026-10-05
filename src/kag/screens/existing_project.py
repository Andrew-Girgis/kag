from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Static

from ..kaggle_api import Competition


DATA_FILE_COUNT_LIMIT = 1000


def _describe_data_dir(data_dir: Path) -> str:
    if not data_dir.is_dir():
        return "missing"
    count = 0
    for path in data_dir.rglob("*"):
        if path.is_file():
            count += 1
            if count >= DATA_FILE_COUNT_LIMIT:
                return f"{DATA_FILE_COUNT_LIMIT}+ files"
    if count == 0:
        return "empty"
    return f"{count} file" if count == 1 else f"{count} files"


class ExistingProjectScreen(Screen):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    class Chosen:
        def __init__(self, competition: Competition, project_path: str, open_existing: bool):
            self.competition = competition
            self.project_path = project_path
            self.open_existing = open_existing

    def __init__(self, competition: Competition, project_dir: Path, **kwargs):
        super().__init__(**kwargs)
        self.competition = competition
        self.project_dir = project_dir

    def _summary_lines(self) -> list[str]:
        notebook = self.project_dir / f"{self.competition.slug}.ipynb"
        data_dir = self.project_dir / "data"
        return [
            f"  Notebook: {'yes' if notebook.exists() else 'missing'}",
            f"  notes.md: {'yes' if (self.project_dir / 'notes.md').exists() else 'missing'}",
            f"  data/: {_describe_data_dir(data_dir)}",
            f"  Git repo: {'yes' if (self.project_dir / '.git').exists() else 'no'}",
        ]

    def compose(self) -> ComposeResult:
        with Vertical(id="existing-dialog"):
            yield Static(
                f"A project for {self.competition.slug} already exists", id="existing-title"
            )
            yield Static(str(self.project_dir), id="existing-path")
            yield Static("\n".join(self._summary_lines()), id="existing-summary")
            yield Static(
                "kag never overwrites your work: it only adds missing files and refreshes "
                "context files it generated that you haven't edited.",
                id="existing-guidance",
            )
            yield ListView(
                ListItem(Label("Open existing project"), id="opt-open"),
                ListItem(Label("Add missing files (keeps your work)"), id="opt-fill"),
                id="existing-options",
            )

    def on_mount(self) -> None:
        options = self.query_one("#existing-options", ListView)
        options.index = 0
        options.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if item_id in ("opt-open", "opt-fill"):
            self.dismiss(
                ExistingProjectScreen.Chosen(
                    self.competition,
                    str(self.project_dir),
                    open_existing=item_id == "opt-open",
                )
            )

    def action_cancel(self) -> None:
        self.dismiss(None)
