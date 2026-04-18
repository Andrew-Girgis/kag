import re
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Static, ListView, ListItem, Label
from textual.binding import Binding
from textual import work
from ..config import Config
from ..kaggle_api import Competition, LocalProject, list_competitions, list_entered_competitions

from datetime import datetime


class CompetitionListScreen(Screen):
    BINDINGS = [
        Binding("escape", "quit", "Quit", show=True),
    ]

    class Selected:
        def __init__(self, competition: Competition, is_local: bool = False, project_path: str | None = None):
            self.competition = competition
            self.is_local = is_local
            self.project_path = project_path

    def __init__(self, config: Config, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.competitions: list[Competition] = []
        self.local_projects: list[LocalProject] = []
        self._loading = False
        self._query = ""

    def compose(self) -> ComposeResult:
        yield Static("🏆 Kaggle Competition Selector", id="title")
        yield Input(placeholder="Type to search competitions...", id="search")
        yield VerticalScroll(id="results")

    def on_mount(self) -> None:
        self.local_projects = self._scan_local()
        self._render_results("")
        self._load_remote()

    @work(thread=True)
    def _load_remote(self) -> None:
        try:
            entered = list_entered_competitions()
            general = list_competitions(group="general")
            combined = entered + general
            seen = set()
            unique = []
            for c in combined:
                if c.slug not in seen:
                    seen.add(c.slug)
                    unique.append(c)
            self.competitions = unique
        except Exception:
            pass
        self.call_from_thread(self._on_remote_loaded)

    def _on_remote_loaded(self) -> None:
        self._loading = False
        self._render_results(self._query)

    def _scan_local(self) -> list[LocalProject]:
        projects = []
        kag_path = self.config.kag_path
        if not kag_path.exists():
            return projects
        for entry in sorted(kag_path.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                try:
                    mtime = entry.stat().st_mtime
                    days = (datetime.now().timestamp() - mtime) / 86400
                    projects.append(LocalProject(
                        name=entry.name,
                        path=str(entry),
                        modified_days_ago=days,
                    ))
                except OSError:
                    continue
        return projects

    def _render_results(self, query: str) -> None:
        self._query = query
        try:
            results = self.query_one("#results", VerticalScroll)
        except Exception:
            return
        results.remove_children()

        shown = 0

        if self.local_projects:
            results.mount(Static("── Local Projects ──", classes="section-header"))
            for p in self.local_projects:
                if query and query.lower() not in p.name.lower():
                    continue
                age = self._format_age(p.modified_days_ago)
                label_text = f"📂 {p.display_title}  {age}"
                safe_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', p.name)
                results.mount(ListItem(Label(label_text), id=f"local-{safe_id}"))
                shown += 1

        if self.competitions:
            results.mount(Static("── Kaggle Competitions ──", classes="section-header"))
            for c in self.competitions:
                q_lower = query.lower()
                if query and q_lower not in c.slug.lower() and q_lower not in c.title.lower():
                    continue
                label_text = f"🏅 {c.display_title}  {c.reward}  {c.deadline}"
                results.mount(ListItem(Label(label_text), id=f"remote-{c.safe_id}"))
                shown += 1

        if not self.competitions and self._loading:
            results.mount(Static("Loading competitions from Kaggle..."))
        elif shown == 0 and query:
            results.mount(Static(f"No matches for '{query}'"))

    def _format_age(self, days: float) -> str:
        if days < 1 / 24:
            return "just now"
        if days < 1:
            return f"{int(days * 24)}h ago"
        if days < 7:
            return f"{int(days)}d ago"
        return f"{int(days / 7)}w ago"

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self._render_results(event.value)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        item_id = item.id
        if not item_id:
            return

        if item_id.startswith("local-"):
            name_key = item_id.removeprefix("local-")
            for p in self.local_projects:
                safe_p = re.sub(r'[^a-zA-Z0-9_\-]', '_', p.name)
                if safe_p == name_key:
                    competition = Competition(
                        slug=p.name,
                        title=p.name,
                        deadline="",
                        reward="",
                        team_count="0",
                    )
                    self.dismiss(CompetitionListScreen.Selected(competition, is_local=True, project_path=p.path))
                    return
        elif item_id.startswith("remote-"):
            slug_key = item_id.removeprefix("remote-")
            for c in self.competitions:
                if c.safe_id == slug_key:
                    self.dismiss(CompetitionListScreen.Selected(competition=c))
                    return

    def action_quit(self) -> None:
        self.app.exit()