from collections.abc import Iterable
from functools import partial

from textual import work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.command import CommandPalette, DiscoveryHit, Hit, Hits, Provider
from textual.screen import Screen
from textual.widgets import Header, Footer

from . import __version__
from .config import THEME_ENV, Config, save_theme
from .kaggle_api import Competition
from .screens.access_required import AccessRequiredScreen
from .screens.competition_list import CompetitionListScreen
from .screens.editor_select import EditorSelectScreen
from .screens.existing_project import ExistingProjectScreen
from .screens.confirm_download import ConfirmDownloadScreen
from .screens.creating_project import CreatingProjectScreen
from .project import existing_project_dir
from .theme import ALIASES, resolve_theme, theme_label, theme_names
from .update_check import UpdateNotice, check_for_update


class ThemeProvider(Provider):
    @property
    def commands(self) -> list[tuple[str, str]]:
        return [
            ("terminal (your terminal's colours)" if name == "terminal" else name, name)
            for name in theme_names()
        ]

    async def discover(self) -> Hits:
        for label, name in self.commands:
            yield DiscoveryHit(label, partial(self.app.choose_theme, name))

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for label, name in self.commands:
            score = matcher.match(label)
            if score > 0:
                yield Hit(score, matcher.highlight(label), partial(self.app.choose_theme, name))


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
    #existing-dialog, #creating-dialog {
        padding: 1 2;
    }
    #creating-title {
        text-style: bold;
    }
    #creating-spinner {
        height: 3;
    }
    #creating-elapsed, #creating-hint {
        color: $text-muted;
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
    App:ansi #helpbar {
        color: ansi_default;
        background: ansi_default;
        border-top: none;
        text-style: dim;
    }
    App:ansi ListView > ListItem.-highlight,
    App:ansi ListView:focus > ListItem.-highlight,
    App:ansi OptionList > .option-list--option-highlighted,
    App:ansi OptionList:focus > .option-list--option-highlighted {
        color: $block-cursor-foreground;
        background: $block-cursor-background;
        text-style: $block-cursor-text-style;
    }
    App:ansi CommandPalette {
        background: ansi_default;
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
        self.messages: list[str] = []
        self.theme, self._theme_warning = resolve_theme(config.theme)
        if self._theme_warning:
            self.messages.append(self._theme_warning)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen(CompetitionListScreen(self.config, initial_query=self.initial_query))
        self._check_for_update()
        if self._theme_warning:
            self.notify(self._theme_warning, severity="warning", timeout=10)

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        yield SystemCommand(
            "Theme", "Change kag's colours (saved for next time)", self.search_themes
        )
        for command in super().get_system_commands(screen):
            if command.title != "Theme":
                yield command

    def search_themes(self) -> None:
        self.push_screen(
            CommandPalette(providers=[ThemeProvider], placeholder="Search for themes…")
        )

    def choose_theme(self, name: str) -> None:
        self.theme = ALIASES.get(name, name)
        label = theme_label(self.theme)
        try:
            path = save_theme(label)
        except Exception as exc:
            self.notify(f"Theme changed, but couldn't save it: {exc}", severity="error")
            return
        message = f"Theme set to {label} and saved to {path}."
        if self.config.theme_source == THEME_ENV:
            message += f" {THEME_ENV} is set, so it overrides this next time."
        self.config.theme = label
        self.notify(message, timeout=6)

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
        self.push_screen(
            CreatingProjectScreen(
                self.config,
                result.competition,
                download_files=result.download_files,
                editor=result.editor,
            ),
            self._on_project_created,
        )

    def _on_project_created(self, result: CreatingProjectScreen.Finished | None) -> None:
        if result is None:
            return
        if result.cancelled:
            self.notify("Project setup cancelled.", timeout=5)
            return
        if result.error is not None or result.project_path is None:
            self.result = None
            self.notify(result.error or "Project creation failed", severity="error", timeout=10)
            self.push_screen(
                ConfirmDownloadScreen(result.competition),
                self._on_download_confirmed,
            )
            return

        self.result = result.project_path
        self.exit()
