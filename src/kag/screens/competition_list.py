from textual import events, work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Input, Static, ListView, ListItem, Label
from textual.binding import Binding
from rich.text import Text
import time
from ..config import Config
from ..kaggle_api import Competition, LocalProject, list_competitions_page, list_entered_competitions

from datetime import datetime


class SafeListView(ListView):
    def _sanitize_index(self) -> None:
        node_count = len(self._nodes)
        if node_count == 0:
            self.index = None
            return
        if self.index is None:
            return
        if self.index < 0:
            self.index = 0
            return
        if self.index >= node_count:
            self.index = node_count - 1

    def action_cursor_up(self) -> None:
        self._sanitize_index()
        super().action_cursor_up()

    def action_cursor_down(self) -> None:
        self._sanitize_index()
        super().action_cursor_down()

    def action_select_cursor(self) -> None:
        self._sanitize_index()
        super().action_select_cursor()


class CompetitionListScreen(Screen):
    BINDINGS = [
        Binding("escape", "quit", "Quit", show=True),
    ]

    class Selected:
        def __init__(self, competition: Competition, is_local: bool = False, project_path: str | None = None):
            self.competition = competition
            self.is_local = is_local
            self.project_path = project_path

    def __init__(self, config: Config, initial_query: str = "", **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.initial_query = initial_query
        self.joined_competitions: list[Competition] = []
        self.all_competitions: list[Competition] = []
        self.local_projects: list[LocalProject] = []
        self._loading = False
        self._query = ""
        self._item_lookup: dict[str, Competition | LocalProject] = {}
        self._render_version = 0
        self._selected_key: str | None = None
        self._all_page = 0
        self._all_has_more = False
        self._all_loading_more = False
        self._helpbar_base = "↑/↓: Navigate  Enter: Select  Esc: Cancel"
        self._spinner_frames = ["|", "/", "-", "\\"]
        self._spinner_index = 0
        self._spinner_message = ""
        self._spinner_timer = None
        self._spinner_stop_timer = None
        self._spinner_started_at = 0.0
        self._spinner_min_visible_seconds = 0.7

    def compose(self) -> ComposeResult:
        title_lines = [
            "▄▄                           ",
            " ██                           ",
            " ██ ▄██▀    ▄█████▄   ▄███▄██ ",
            " ██▄██      ▀ ▄▄▄██  ██▀  ▀██ ",
            " ██▀██▄    ▄██▀▀▀██  ██    ██ ",
            " ██  ▀█▄   ██▄▄▄███  ▀██▄▄███ ",
            " ▀▀   ▀▀▀   ▀▀▀▀ ▀▀   ▄▀▀▀ ██ ",
            "                      ▀████▀▀ ",
        ]
        yield Static(
            "\n".join(title_lines),
            id="title",
        )
        yield Static(
            "Fields: [bold cyan]Competition[/bold cyan]  |  [green]Prize[/green]  |  [magenta]Deadline[/magenta]",
            id="legend",
        )
        yield Input(placeholder="Type to search competitions...", id="search")
        yield SafeListView(id="results")
        yield Static(self._helpbar_base, id="helpbar")

    def _list_view(self) -> SafeListView | None:
        try:
            return self.query_one("#results", SafeListView)
        except Exception:
            return None

    def _helpbar_widget(self) -> Static | None:
        try:
            return self.query_one("#helpbar", Static)
        except Exception:
            return None

    def _set_helpbar(self, text: str) -> None:
        widget = self._helpbar_widget()
        if widget is not None:
            widget.update(text)

    def _tick_spinner(self) -> None:
        frame = self._spinner_frames[self._spinner_index % len(self._spinner_frames)]
        self._spinner_index += 1
        self._set_helpbar(f"{self._helpbar_base}  |  {frame} {self._spinner_message}")

    def _start_spinner(self, message: str) -> None:
        if self._spinner_stop_timer is not None:
            self._spinner_stop_timer.stop()
            self._spinner_stop_timer = None
        self._spinner_message = message
        self._spinner_index = 0
        self._spinner_started_at = time.monotonic()
        self._tick_spinner()
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
        self._spinner_timer = self.set_interval(0.12, self._tick_spinner)

    def _stop_spinner_now(self) -> None:
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        if self._spinner_stop_timer is not None:
            self._spinner_stop_timer.stop()
            self._spinner_stop_timer = None
        self._spinner_message = ""
        self._set_helpbar(self._helpbar_base)

    def _stop_spinner(self) -> None:
        if self._spinner_timer is None:
            self._set_helpbar(self._helpbar_base)
            return
        elapsed = time.monotonic() - self._spinner_started_at
        remaining = self._spinner_min_visible_seconds - elapsed
        if remaining > 0:
            if self._spinner_stop_timer is not None:
                self._spinner_stop_timer.stop()
            self._spinner_stop_timer = self.set_timer(remaining, self._stop_spinner_now)
            return
        self._stop_spinner_now()

    def _stable_key(self, item: Competition | LocalProject) -> str:
        if isinstance(item, LocalProject):
            return f"local:{item.path}"
        return f"competition:{item.slug}"

    def _first_selectable_index(self, list_view: ListView) -> int | None:
        selectable_ids = set(self._item_lookup.keys())
        for idx, child in enumerate(list_view.children):
            child_id = getattr(child, "id", None)
            if child_id in selectable_ids:
                return idx
        return None

    def _last_selectable_index(self, list_view: ListView) -> int | None:
        selectable_ids = set(self._item_lookup.keys())
        for idx in range(len(list_view.children) - 1, -1, -1):
            child_id = getattr(list_view.children[idx], "id", None)
            if child_id in selectable_ids:
                return idx
        return None

    def _focus_list_for_navigation(self, direction: str) -> bool:
        search = self.query_one("#search", Input)
        if not search.has_focus:
            return False
        list_view = self._list_view()
        if list_view is None:
            return False
        child_count = len(list_view.children)
        if child_count == 0:
            return False
        if list_view.index is not None and (list_view.index < 0 or list_view.index >= child_count):
            list_view.index = None
        list_view.focus()
        if direction == "down":
            list_view.index = self._first_selectable_index(list_view)
        elif direction == "up":
            list_view.index = self._last_selectable_index(list_view)
        return True

    def on_mount(self) -> None:
        self.local_projects = self._scan_local()
        self._loading = True
        self._start_spinner("Searching Kaggle competitions...")
        self._render_results(self.initial_query)
        if self.initial_query:
            search = self.query_one("#search", Input)
            search.value = self.initial_query
        else:
            search = self.query_one("#search", Input)
            search.focus()
        self._load_remote()

    @work(thread=True)
    def _load_remote(self) -> None:
        joined: list[Competition] = []
        all_competitions: list[Competition] = []
        all_has_more = False
        all_page = 1
        try:
            joined = list_entered_competitions()
            general, all_has_more = list_competitions_page(
                group="general",
                page=all_page,
                page_size=20,
            )
            joined_slugs = {competition.slug for competition in joined}
            seen_general = set()
            for competition in general:
                if competition.slug in joined_slugs:
                    continue
                if competition.slug in seen_general:
                    continue
                seen_general.add(competition.slug)
                all_competitions.append(competition)
        except Exception:
            pass
        self.app.call_from_thread(self._on_remote_loaded, joined, all_competitions, all_has_more, all_page)

    def _on_remote_loaded(
        self,
        joined: list[Competition],
        all_competitions: list[Competition],
        all_has_more: bool,
        all_page: int,
    ) -> None:
        self.joined_competitions = joined
        self.all_competitions = all_competitions
        self._all_has_more = all_has_more
        self._all_page = all_page
        self._all_loading_more = False
        self._loading = False
        self._stop_spinner()
        self._render_results(self._query)

    @work(thread=True)
    def _load_more_all(self) -> None:
        next_page = self._all_page + 1
        new_competitions: list[Competition] = []
        has_more = False
        try:
            general_page, has_more = list_competitions_page(
                group="general",
                page=next_page,
                page_size=20,
            )
            existing_slugs = {competition.slug for competition in self.joined_competitions}
            existing_slugs.update(competition.slug for competition in self.all_competitions)
            for competition in general_page:
                if competition.slug in existing_slugs:
                    continue
                existing_slugs.add(competition.slug)
                new_competitions.append(competition)
        except Exception:
            has_more = False
        self.app.call_from_thread(self._on_more_loaded, next_page, new_competitions, has_more)

    def _on_more_loaded(self, page: int, new_competitions: list[Competition], has_more: bool) -> None:
        if new_competitions:
            self.all_competitions.extend(new_competitions)
        self._all_page = page
        self._all_has_more = has_more
        self._all_loading_more = False
        self._stop_spinner()
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
        self._render_version += 1
        previous_selected_key = self._selected_key
        self._item_lookup.clear()
        try:
            results = self.query_one("#results", SafeListView)
        except Exception:
            return
        results.remove_children()
        results.index = None

        shown = 0
        q_lower = query.lower()

        if self._loading:
            results.mount(
                ListItem(
                    Label("Loading competitions from Kaggle..."),
                    id=f"info-{self._render_version}-loading",
                    disabled=True,
                )
            )

        if self.local_projects:
            local_filtered = [p for p in self.local_projects if (not query or q_lower in p.name.lower())]
            if local_filtered:
                local_count = len(self.local_projects)
                results.mount(
                    ListItem(
                        Label(f"── Your notebooks ({local_count}) ──"),
                        id=f"header-{self._render_version}-local",
                        disabled=True,
                    )
                )
            for idx, p in enumerate(local_filtered):
                age = self._format_age(p.modified_days_ago)
                label_text = Text()
                label_text.append("📂 ", style="blue")
                label_text.append(p.display_title, style="bold blue")
                label_text.append("  |  ", style="dim")
                label_text.append(age, style="dim")
                label_text.append("  |  ", style="dim")
                label_text.append("LOCAL", style="bold blue")
                item_id = f"local-{self._render_version}-{idx}"
                self._item_lookup[item_id] = p
                results.mount(ListItem(Label(label_text), id=item_id))
                shown += 1

        if self.joined_competitions:
            joined_filtered = [
                c for c in self.joined_competitions
                if (not query or q_lower in c.slug.lower() or q_lower in c.title.lower())
            ]
            if joined_filtered:
                joined_count = len(self.joined_competitions)
                results.mount(
                    ListItem(
                        Label(f"── Joined competitions ({joined_count}) ──"),
                        id=f"header-{self._render_version}-joined",
                        disabled=True,
                    )
                )
            for idx, c in enumerate(joined_filtered):
                label_text = Text()
                label_text.append("🏅 ", style="yellow")
                label_text.append(c.display_title, style="bold cyan")
                label_text.append("  |  ", style="dim")
                label_text.append(c.reward or "n/a", style="green")
                label_text.append("  |  ", style="dim")
                label_text.append(c.deadline or "n/a", style="magenta")
                item_id = f"joined-{self._render_version}-{idx}"
                self._item_lookup[item_id] = c
                results.mount(ListItem(Label(label_text), id=item_id))
                shown += 1

        if self.all_competitions or self._all_has_more or self._all_loading_more:
            all_filtered = [
                c for c in self.all_competitions
                if (not query or q_lower in c.slug.lower() or q_lower in c.title.lower())
            ]
            if all_filtered or self._all_has_more or self._all_loading_more:
                all_count = len(self.all_competitions)
                all_suffix = "+" if (self._all_has_more or self._all_loading_more) else ""
                results.mount(
                    ListItem(
                        Label(f"── All competitions ({all_count}{all_suffix}) ──"),
                        id=f"header-{self._render_version}-all",
                        disabled=True,
                    )
                )
            for idx, c in enumerate(all_filtered):
                label_text = Text()
                label_text.append("🏁 ", style="yellow")
                label_text.append(c.display_title, style="bold cyan")
                label_text.append("  |  ", style="dim")
                label_text.append(c.reward or "n/a", style="green")
                label_text.append("  |  ", style="dim")
                label_text.append(c.deadline or "n/a", style="magenta")
                item_id = f"all-{self._render_version}-{idx}"
                self._item_lookup[item_id] = c
                results.mount(ListItem(Label(label_text), id=item_id))
                shown += 1

            if self._all_loading_more:
                results.mount(
                    ListItem(
                        Label("Loading more competitions..."),
                        id=f"info-{self._render_version}-more-loading",
                        disabled=True,
                    )
                )
            elif self._all_has_more:
                results.mount(
                    ListItem(
                        Label("↓ Reach end of list to load more"),
                        id=f"info-{self._render_version}-more",
                        disabled=True,
                    )
                )

        if shown == 0 and not self._loading:
            if query:
                results.mount(
                    ListItem(
                        Label(f"No matches for '{query}'"),
                        id=f"info-{self._render_version}-nomatch",
                        disabled=True,
                    )
                )
            else:
                results.mount(
                    ListItem(
                        Label("No competitions found."),
                        id=f"info-{self._render_version}-empty",
                        disabled=True,
                    )
                )

        target_index = None
        if previous_selected_key:
            for idx, child in enumerate(results.children):
                child_id = getattr(child, "id", None)
                if not child_id:
                    continue
                lookup_item = self._item_lookup.get(child_id)
                if lookup_item and self._stable_key(lookup_item) == previous_selected_key:
                    target_index = idx
                    break
        if target_index is None:
            target_index = self._first_selectable_index(results)
        results.index = target_index

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

    def on_key(self, event: events.Key) -> None:
        if event.key == "down" and self._focus_list_for_navigation("down"):
            event.stop()
            return
        if event.key == "up" and self._focus_list_for_navigation("up"):
            event.stop()
            return
        if event.key == "enter":
            search = self.query_one("#search", Input)
            if search.has_focus and self._focus_list_for_navigation("down"):
                event.stop()
                return

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        render_version_at_event = self._render_version
        item_id = getattr(event.item, "id", None)
        if not item_id:
            return
        selected = self._item_lookup.get(item_id)
        if selected is None:
            return
        self._selected_key = self._stable_key(selected)

        list_view = self._list_view()
        if list_view is None:
            return
        if render_version_at_event != self._render_version:
            return
        last_index = self._last_selectable_index(list_view)
        current_index = list_view.index
        if (
            not self._loading
            and self._all_has_more
            and not self._all_loading_more
            and last_index is not None
            and current_index is not None
            and current_index == last_index
        ):
            self._all_loading_more = True
            self._start_spinner("Loading more competitions...")
            self._render_results(self._query)
            self._load_more_all()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        item_id = item.id
        if not item_id:
            return

        selected = self._item_lookup.get(item_id)
        if selected is None:
            return

        if isinstance(selected, LocalProject):
            competition = Competition(
                slug=selected.name,
                title=selected.name,
                deadline="",
                reward="",
                team_count="0",
            )
            self.dismiss(CompetitionListScreen.Selected(competition, is_local=True, project_path=selected.path))
            return

        if isinstance(selected, Competition):
            self.dismiss(CompetitionListScreen.Selected(competition=selected))
            return

    def action_quit(self) -> None:
        self._stop_spinner()
        self.app.exit()
