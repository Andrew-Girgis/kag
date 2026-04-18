from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from .config import Config
from .screens.competition_list import CompetitionListScreen
from .screens.editor_select import EditorSelectScreen
from .screens.confirm_download import ConfirmDownloadScreen
from .project import create_project


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
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, config: Config, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.result: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen(CompetitionListScreen(self.config), self._on_competition_selected)

    def _on_competition_selected(self, result: CompetitionListScreen.Selected | None) -> None:
        if result is None:
            return
        if result.is_local:
            self.result = result.project_path
            self.exit()
            return
        self.push_screen(
            ConfirmDownloadScreen(result.competition),
            self._on_download_confirmed,
        )

    def _on_download_confirmed(self, result: ConfirmDownloadScreen.Confirmed | None) -> None:
        if result is None:
            return
        self.push_screen(
            EditorSelectScreen(self.config, result.competition, result.download_files),
            self._on_editor_selected,
        )

    def _on_editor_selected(self, result: EditorSelectScreen.Selected | None) -> None:
        if result is None:
            return
        project_dir = create_project(
            competition=result.competition,
            config=self.config,
            download_files=result.download_files,
            editor=result.editor,
        )
        self.result = project_dir
        self.exit()