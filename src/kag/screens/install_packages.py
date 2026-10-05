from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Static

from ..config import Config
from ..environment import PYPROJECT_NAME, describe, install_commands, planned_packages
from ..kaggle_api import Competition


class InstallPackagesScreen(Screen):
    BINDINGS = [
        Binding("y", "install", "Install", show=True),
        Binding("n", "skip", "Skip", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    class Chosen:
        def __init__(
            self,
            competition: Competition,
            download_files: bool,
            editor: str | None,
            install: bool,
        ):
            self.competition = competition
            self.download_files = download_files
            self.editor = editor
            self.install = install

    def __init__(
        self,
        config: Config,
        competition: Competition,
        download_files: bool,
        editor: str | None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.config = config
        self.competition = competition
        self.download_files = download_files
        self.editor = editor

    def compose(self) -> ComposeResult:
        environment = self.config.environment
        project_dir = self.config.kag_path / self.competition.slug
        existing = (project_dir / PYPROJECT_NAME).exists()
        packages = planned_packages(project_dir, self.config)
        source = " listed in the project's existing pyproject.toml" if existing else ""
        if environment.command:
            question = "Run this command to set up the project's Python environment?"
        elif packages is None:
            question = (
                "Install the packages in the project's existing pyproject.toml? "
                "kag couldn't read it to list them."
            )
        elif packages:
            noun = "package" if len(packages) == 1 else "packages"
            question = f"Install {len(packages)} {noun}{source} from PyPI into .venv?"
        else:
            question = "Create an empty .venv for the project?"
        with Vertical(id="install-dialog"):
            yield Static(question, id="install-title")
            if packages and not environment.command:
                yield Static(", ".join(packages), id="install-packages")
            yield Static(
                f"Command: {describe(install_commands(environment))}", id="install-command"
            )
            yield Static(
                "Installing runs code from these packages. Change the list, or set "
                'install = "always" or "never", under [environment] in ~/.kag_config.toml.',
                id="install-hint",
            )
            yield ListView(
                ListItem(Label("No, just write pyproject.toml (N)"), id="install-no"),
                ListItem(Label("Yes, install now (y)"), id="install-yes"),
                id="install-options",
            )

    def on_mount(self) -> None:
        options = self.query_one("#install-options", ListView)
        options.index = 0
        options.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self._choose(event.item.id == "install-yes")

    def _choose(self, install: bool) -> None:
        self.dismiss(
            InstallPackagesScreen.Chosen(
                competition=self.competition,
                download_files=self.download_files,
                editor=self.editor,
                install=install,
            )
        )

    def action_install(self) -> None:
        self._choose(True)

    def action_skip(self) -> None:
        self._choose(False)

    def action_cancel(self) -> None:
        self.dismiss(None)
