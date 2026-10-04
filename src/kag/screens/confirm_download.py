from textual.app import ComposeResult
from textual.screen import Screen
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static, Label, ListView, ListItem

from ..kaggle_api import (
    Competition,
    FileListResult,
    check_competition_access,
    list_competition_files,
)
from textual import work


class ConfirmDownloadScreen(Screen):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    class Confirmed:
        def __init__(
            self,
            competition: Competition,
            download_files: bool,
            access_ok: bool = True,
            access_details: str = "",
        ):
            self.competition = competition
            self.download_files = download_files
            self.access_ok = access_ok
            self.access_details = access_details

    def __init__(self, competition: Competition, **kwargs):
        super().__init__(**kwargs)
        self.competition = competition
        self.files: list[str] = []
        self._files_listed = False
        self._checking_access = False

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(f"📥 {self.competition.title}", id="comp-title")
            yield Static(f"Slug: {self.competition.slug}", id="comp-slug")
            if self.competition.reward:
                yield Static(f"Reward: {self.competition.reward}")
            if self.competition.deadline:
                yield Static(f"Deadline: {self.competition.deadline}")
            yield Static("Checking downloadable files...", id="comp-files")
            yield Static(
                "Checking whether this competition has downloadable files...",
                id="download-question",
            )
            yield ListView(
                ListItem(Label("Checking files..."), id="opt-loading", disabled=True),
                id="download-options",
            )

    def on_mount(self) -> None:
        self._load_files()
        options = self.query_one("#download-options", ListView)
        options.index = 0
        options.focus()

    @work(thread=True)
    def _load_files(self) -> None:
        result = list_competition_files(self.competition.slug)
        self.app.call_from_thread(self._on_files_loaded, result)

    def _on_files_loaded(self, result: FileListResult) -> None:
        self.files = list(result.files) if result.success else []
        self._files_listed = result.success
        try:
            files_widget = self.query_one("#comp-files", Static)
            question_widget = self.query_one("#download-question", Static)
            options = self.query_one("#download-options", ListView)
        except Exception:
            return

        if result.success and not self.files:
            files_widget.update("Files:\n  No downloadable files found.")
            question_widget.update("Continuing without download.")
            self.dismiss(ConfirmDownloadScreen.Confirmed(self.competition, download_files=False))
            return

        if result.success:
            file_list = "\n".join(
                f"  - {file.name} ({file.display_size})" for file in result.files[:10]
            )
            if len(result.files) > 10:
                file_list += f"\n  ... and {len(result.files) - 10} more"
            if result.truncated:
                file_list += f"\n  (list truncated: {result.details})"
            files_widget.update(f"Files:\n{file_list}")
        else:
            files_widget.update(f"Files:\n  Could not list files: {result.details}")

        question_widget.update("Download competition files?")
        options.remove_children()
        options.mount(ListItem(Label("Yes, download"), id="opt-yes"))
        options.mount(ListItem(Label("No, skip download"), id="opt-no"))
        options.index = 0

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if self._checking_access:
            return
        item_id = event.item.id
        if item_id == "opt-yes":
            if self._files_listed:
                self.dismiss(ConfirmDownloadScreen.Confirmed(self.competition, download_files=True))
                return
            self._checking_access = True
            self.query_one("#download-question", Static).update("Checking access with Kaggle...")
            self.query_one("#download-options", ListView).disabled = True
            self._check_access()
        elif item_id == "opt-no":
            self.dismiss(ConfirmDownloadScreen.Confirmed(self.competition, download_files=False))

    @work(thread=True)
    def _check_access(self) -> None:
        access_ok, details = check_competition_access(self.competition.slug)
        self.app.call_from_thread(self._on_access_checked, access_ok, details)

    def _on_access_checked(self, access_ok: bool, details: str) -> None:
        self._checking_access = False
        self.dismiss(
            ConfirmDownloadScreen.Confirmed(
                self.competition,
                download_files=True,
                access_ok=access_ok,
                access_details=details,
            )
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
