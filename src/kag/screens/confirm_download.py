from textual.app import ComposeResult
from textual.screen import Screen
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static, Label

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
            with Horizontal(id="buttons"):
                yield Button("Yes, download", variant="primary", id="btn-yes")
                yield Button("No, skip download", variant="default", id="btn-no")

    def on_mount(self) -> None:
        self._load_files()

    @work(exclusive=True)
    async def _load_files(self) -> None:
        self.files = get_competition_files(self.competition.slug)
        try:
            files_widget = self.query_one("#comp-files", Static)
            if self.files:
                file_list = "\n".join(f"  - {f}" for f in self.files[:10])
                if len(self.files) > 10:
                    file_list += f"\n  ... and {len(self.files) - 10} more"
                files_widget.update(f"Files:\n{file_list}")
            else:
                files_widget.update("Files: (will be listed after download)")
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-yes":
            self.dismiss(ConfirmDownloadScreen.Confirmed(self.competition, download_files=True))
        elif event.button.id == "btn-no":
            self.dismiss(ConfirmDownloadScreen.Confirmed(self.competition, download_files=False))

    def action_cancel(self) -> None:
        self.app.pop_screen()