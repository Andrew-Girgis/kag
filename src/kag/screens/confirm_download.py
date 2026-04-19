from textual.app import ComposeResult
from textual.screen import Screen
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static, Label, ListView, ListItem

from ..kaggle_api import Competition, get_competition_files
from textual import work


class ConfirmDownloadScreen(Screen):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    class Confirmed:
        def __init__(self, competition: Competition, download_files: bool):
            self.competition = competition
            self.download_files = download_files

    def __init__(self, competition: Competition, **kwargs):
        super().__init__(**kwargs)
        self.competition = competition
        self.files: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(f"📥 {self.competition.title}", id="comp-title")
            yield Static(f"Slug: {self.competition.slug}", id="comp-slug")
            if self.competition.reward:
                yield Static(f"Reward: {self.competition.reward}")
            if self.competition.deadline:
                yield Static(f"Deadline: {self.competition.deadline}")
            yield Static("", id="comp-files")
            yield Static("Download competition files?", id="download-question")
            yield ListView(
                ListItem(Label("Yes, download"), id="opt-yes"),
                ListItem(Label("No, skip download"), id="opt-no"),
                id="download-options",
            )

    def on_mount(self) -> None:
        self._load_files()
        options = self.query_one("#download-options", ListView)
        options.index = 0
        options.focus()

    @work(thread=True)
    def _load_files(self) -> None:
        files = get_competition_files(self.competition.slug)
        self.app.call_from_thread(self._on_files_loaded, files)

    def _on_files_loaded(self, files: list[str]) -> None:
        self.files = files
        try:
            files_widget = self.query_one("#comp-files", Static)
        except Exception:
            return

        if self.files:
            file_list = "\n".join(f"  - {f}" for f in self.files[:10])
            if len(self.files) > 10:
                file_list += f"\n  ... and {len(self.files) - 10} more"
        else:
            file_list = "(will be listed after download)"
        files_widget.update(f"Files:\n{file_list}")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if item_id == "opt-yes":
            self.dismiss(ConfirmDownloadScreen.Confirmed(self.competition, download_files=True))
        elif item_id == "opt-no":
            self.dismiss(ConfirmDownloadScreen.Confirmed(self.competition, download_files=False))

    def action_cancel(self) -> None:
        self.dismiss(None)
