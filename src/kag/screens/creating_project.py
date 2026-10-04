import threading
import time

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import LoadingIndicator, Static

from ..config import Config
from ..kaggle_api import Competition
from ..project import ProjectCreationCancelled, ProjectCreationError, create_project


def _format_elapsed(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class CreatingProjectScreen(Screen):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    class Finished:
        def __init__(
            self,
            competition: Competition,
            project_path: str | None = None,
            error: str | None = None,
            cancelled: bool = False,
        ):
            self.competition = competition
            self.project_path = project_path
            self.error = error
            self.cancelled = cancelled

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
        self.status = "Starting..."
        self._cancel = threading.Event()
        self._started_at = 0.0

    def compose(self) -> ComposeResult:
        with Vertical(id="creating-dialog"):
            yield Static(f"Setting up {self.competition.slug}", id="creating-title")
            yield LoadingIndicator(id="creating-spinner")
            yield Static(self.status, id="creating-status")
            yield Static("Elapsed 0:00", id="creating-elapsed")
            yield Static("Esc: cancel and clean up", id="creating-hint")

    def on_mount(self) -> None:
        self._started_at = time.monotonic()
        self.set_interval(1, self._tick)
        self._create()

    def _tick(self) -> None:
        elapsed = _format_elapsed(time.monotonic() - self._started_at)
        try:
            self.query_one("#creating-elapsed", Static).update(f"Elapsed {elapsed}")
        except Exception:
            return

    def _set_status(self, message: str) -> None:
        if self._cancel.is_set():
            message = "Cancelling..."
        self.status = message
        try:
            self.query_one("#creating-status", Static).update(message)
        except Exception:
            return

    def _report(self, message: str) -> None:
        try:
            self.app.call_from_thread(self._set_status, message)
        except Exception:
            return

    def on_unmount(self) -> None:
        self._cancel.set()

    @work(thread=True, exclusive=True)
    def _create(self) -> None:
        try:
            project_path = create_project(
                competition=self.competition,
                config=self.config,
                download_files=self.download_files,
                editor=self.editor,
                progress=self._report,
                cancel=self._cancel,
            )
            result = CreatingProjectScreen.Finished(self.competition, project_path=project_path)
        except ProjectCreationCancelled:
            result = CreatingProjectScreen.Finished(self.competition, cancelled=True)
        except ProjectCreationError as exc:
            result = CreatingProjectScreen.Finished(self.competition, error=str(exc))
        except Exception as exc:
            result = CreatingProjectScreen.Finished(
                self.competition,
                error=f"Project creation failed: {exc or type(exc).__name__}",
            )
        try:
            self.app.call_from_thread(self.dismiss, result)
        except Exception:
            return

    def action_cancel(self) -> None:
        if self._cancel.is_set():
            return
        self._cancel.set()
        self._set_status("Cancelling...")
