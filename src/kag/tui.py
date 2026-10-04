from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from . import __version__
from .config import Config
from .kaggle_api import Competition
from .screens.access_required import AccessRequiredScreen
from .screens.competition_list import CompetitionListScreen
from .screens.editor_select import EditorSelectScreen
from .screens.existing_project import ExistingProjectScreen
from .screens.confirm_download import ConfirmDownloadScreen
from .project import ProjectCreationError, create_project, existing_project_dir
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
    #existing-dialog {
        padding: 1 2;
    }
    #existing-title {
        text-style: bold;
    }
    #existing-path {
        color: $text-muted;
    }
    #existing-summary, #existing-guidance {
        padding: 1 0 0 0;
    }
    #existing-options {
        margin: 1 0 0 0;
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
        self.push_screen(CompetitionListScreen(self.config, initial_query=self.initial_query))
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

    def on_competition_list_screen_selected(self, message: CompetitionListScreen.Selected) -> None:
        self._on_competition_selected(message)

    def _on_competition_selected(self, result: CompetitionListScreen.Selected | None) -> None:
        if result is None:
            return
        if result.is_local:
            self.result = result.project_path
            self.exit()
            return
        existing_dir = existing_project_dir(self.config, result.competition.slug)
        if existing_dir is not None:
            self.push_screen(
                ExistingProjectScreen(result.competition, existing_dir),
                self._on_existing_project_chosen,
            )
            return
        self._start_project_flow(result.competition)

    def _on_existing_project_chosen(self, result: ExistingProjectScreen.Chosen | None) -> None:
        if result is None:
            return
        if result.open_existing:
            self.result = result.project_path
            self.exit()
            return
        self._start_project_flow(result.competition)

    def _start_project_flow(self, competition: Competition) -> None:
        if not competition.is_joined:
            self.push_screen(
                AccessRequiredScreen(
                    competition,
                    "Please join this competition and accept its rules before downloading data.",
                ),
                self._on_access_resolved,
            )
            return

        self.push_screen(
            ConfirmDownloadScreen(competition),
            self._on_download_confirmed,
        )

    def _on_download_confirmed(self, result: ConfirmDownloadScreen.Confirmed | None) -> None:
        if result is None:
            return
        if result.download_files and not result.access_ok:
            self.push_screen(
                AccessRequiredScreen(result.competition, result.access_details),
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
        except Exception as exc:
            message = (
                str(exc)
                if isinstance(exc, ProjectCreationError)
                else f"Project creation failed: {exc or type(exc).__name__}"
            )
            self.result = None
            self.notify(message, severity="error", timeout=10)
            self.push_screen(
                ConfirmDownloadScreen(result.competition),
                self._on_download_confirmed,
            )
            return

        self.result = project_dir
        self.exit()
