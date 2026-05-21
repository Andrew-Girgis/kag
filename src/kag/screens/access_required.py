from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Static

from ..kaggle_api import Competition, check_competition_access, open_competition_page


class AccessRequiredScreen(Screen):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    class Resolved:
        def __init__(self, competition: Competition, download_files: bool, is_joined: bool = False):
            competition.is_joined = is_joined
            self.competition = competition
            self.download_files = download_files

    def __init__(self, competition: Competition, details: str, **kwargs):
        super().__init__(**kwargs)
        self.competition = competition
        self.details = details

    def compose(self) -> ComposeResult:
        with Vertical(id="access-dialog"):
            yield Static(f"Access required for {self.competition.slug}", id="access-title")
            yield Static(
                "To download data, you need to join this competition and accept its rules on Kaggle.",
                id="access-guidance",
            )
            yield Static(f"Kaggle said: {self.details}", id="access-details")
            yield Static(
                "If you choose no, kag will continue without downloading data for this project.",
                id="access-warning",
            )
            yield ListView(
                ListItem(Label("Yes, open Kaggle to join"), id="opt-join"),
                ListItem(Label("I already joined"), id="opt-already-joined"),
                ListItem(Label("No, continue without data"), id="opt-skip"),
                id="access-options",
            )

    def on_mount(self) -> None:
        options = self.query_one("#access-options", ListView)
        options.index = 0
        options.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if item_id == "opt-join":
            open_competition_page(self.competition.slug, "overview")
            open_competition_page(self.competition.slug, "rules")
            self._retry_access()
        elif item_id == "opt-already-joined":
            self._retry_access()
        elif item_id == "opt-skip":
            self.dismiss(AccessRequiredScreen.Resolved(self.competition, download_files=False))

    def _retry_access(self) -> None:
        access_ok, details = check_competition_access(self.competition.slug)
        if access_ok:
            self.dismiss(
                AccessRequiredScreen.Resolved(self.competition, download_files=True, is_joined=True)
            )
            return

        self.details = details
        try:
            details_widget = self.query_one("#access-details", Static)
        except Exception:
            return
        details_widget.update(f"Kaggle said: {self.details}")

    def action_cancel(self) -> None:
        self.dismiss(None)
