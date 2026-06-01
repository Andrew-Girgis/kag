from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from . import __version__
from .config import Config
from .kaggle_api import check_competition_access
from .screens.access_required import AccessRequiredScreen
from .screens.competition_list import CompetitionListScreen
from .screens.editor_select import EditorSelectScreen
from .screens.confirm_download import ConfirmDownloadScreen
from .project import ProjectCreationError, create_project
from .update_check import UpdateNotice, check_for_update


class KagApp(App):
    TITLE = "kag"
    SUB_TITLE = "Kaggle Competition Bootstrapper"
    CSS = """
    Screen {
        align: center middle;
    }
    #title {
        text-align: center;
        padding: 1;
        text-style: bold;
        color: #22beff;
        text-wrap: nowrap;
    }
    #legend {
        text-align: center;
        color: $text-muted;
        padding: 0 1 1 1;
    }
    .section-header {
        color: $text-muted;
        text-style: italic;
        padding: 1 0 0 2;
    }
    #comp-title {
        text-style: bold;
        padding: 1 0 0 2;
    }
    #download-question {
        padding: 1 0;
    }
    #buttons {
        padding: 1;
    }
    #confirm-dialog {
        padding: 1 2;
    }
    #editor-title {
        text-style: bold;
        padding: 1 0;
    }
    #helpbar {
        dock: bottom;
        width: 100%;
        padding: 0 1;
        color: $text-muted;
        background: $panel;
        border-top: solid $surface-lighten-2;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self, config: Config, initial_query: str = "", **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.initial_query = initial_query
        self.result: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen(
            CompetitionListScreen(self.config, initial_query=self.initial_query),
            self._on_competition_selected,
        )
        self._check_for_update()

    @work(thread=True)
    def _check_for_update(self) -> None:
        notice = check_for_update(__version__, self.config)
        if notice is not None:
            self.call_from_thread(self._show_update_notice, notice)

    def _show_update_notice(self, notice: UpdateNotice | None) -> None:
        if notice is None:
            return
        self.notify(notice.message, severity="information", timeout=12)

    def _on_competition_selected(self, result: CompetitionListScreen.Selected | None) -> None:
        if result is None:
            return
        if result.is_local:
            self.result = result.project_path
            self.exit()
            return
        if not result.competition.is_joined:
            self.push_screen(
                AccessRequiredScreen(
                    result.competition,
                    "Please join this competition and accept its rules before downloading data.",
                ),
                self._on_access_resolved,
            )
            return

        self.push_screen(
            ConfirmDownloadScreen(result.competition),
            self._on_download_confirmed,
        )

    def _on_download_confirmed(self, result: ConfirmDownloadScreen.Confirmed | None) -> None:
        if result is None:
            return
        if result.download_files:
            access_ok, access_details = check_competition_access(result.competition.slug)
            if not access_ok:
                self.push_screen(
                    AccessRequiredScreen(result.competition, access_details),
                    self._on_access_resolved,
                )
                return

        self.push_screen(
            EditorSelectScreen(self.config, result.competition, result.download_files),
            self._on_editor_selected,
        )

    def _on_access_resolved(self, result: AccessRequiredScreen.Resolved | None) -> None:
        if result is None:
            return
        if result.download_files:
            self.push_screen(
                ConfirmDownloadScreen(result.competition),
                self._on_download_confirmed,
            )
            return

        self.push_screen(
            EditorSelectScreen(self.config, result.competition, result.download_files),
            self._on_editor_selected,
        )

    def _on_editor_selected(self, result: EditorSelectScreen.Selected | None) -> None:
        if result is None:
            return
        try:
            project_dir = create_project(
                competition=result.competition,
                config=self.config,
                download_files=result.download_files,
                editor=result.editor,
            )
        except ProjectCreationError as exc:
            self.result = None
            self.notify(str(exc), severity="error", timeout=10)
            self.push_screen(
                ConfirmDownloadScreen(result.competition),
                self._on_download_confirmed,
            )
            return

        self.result = project_dir
        self.exit()
