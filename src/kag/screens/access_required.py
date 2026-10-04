from textual import work
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
        self._checking_access = False

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
        if self._checking_access:
            return
        self._checking_access = True
        self._set_checking(True)
        self._check_access()

    @work(thread=True)
    def _check_access(self) -> None:
        access_ok, details = check_competition_access(self.competition.slug)
        self.app.call_from_thread(self._on_access_checked, access_ok, details)

    def _on_access_checked(self, access_ok: bool, details: str) -> None:
        self._checking_access = False
        if access_ok:
            self.dismiss(
                AccessRequiredScreen.Resolved(self.competition, download_files=True, is_joined=True)
            )
            return

        self.details = details
        self._set_checking(False)

    def _set_checking(self, checking: bool) -> None:
        try:
            details_widget = self.query_one("#access-details", Static)
            options = self.query_one("#access-options", ListView)
        except Exception:
            return
        details_widget.update(
            "Checking access with Kaggle..." if checking else f"Kaggle said: {self.details}"
        )
        options.disabled = checking

    def action_cancel(self) -> None:
        self.dismiss(None)
