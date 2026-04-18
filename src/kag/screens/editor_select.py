from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import ListItem, Label, ListView, Static
from textual.binding import Binding

from ..config import Config
from ..kaggle_api import Competition


class EditorSelectScreen(Screen):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    class Selected:
        def __init__(self, competition: Competition, download_files: bool, editor: str | None):
            self.competition = competition
            self.download_files = download_files
            self.editor = editor

    def __init__(self, config: Config, competition: Competition, download_files: bool, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.competition = competition
        self.download_files = download_files
        self.editors = config.available_editors()

    def compose(self) -> ComposeResult:
        yield Static(f"🖥 Open {self.competition.slug} with...", id="editor-title")
        items = []
        for ed in self.editors:
            items.append(ListItem(Label(f"{ed['name']} ({ed['cmd']})"), id=f"editor-{ed['key']}"))
        items.append(ListItem(Label("Terminal only (no editor)"), id="editor-none"))
        yield ListView(*items, id="editor-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if item_id == "editor-none":
            self.dismiss(EditorSelectScreen.Selected(
                competition=self.competition,
                download_files=self.download_files,
                editor=None,
            ))
        elif item_id and item_id.startswith("editor-"):
            key = item_id.removeprefix("editor-")
            editor_cmd = None
            for ed in self.editors:
                if ed["key"] == key:
                    editor_cmd = ed["cmd"]
                    break
            self.dismiss(EditorSelectScreen.Selected(
                competition=self.competition,
                download_files=self.download_files,
                editor=editor_cmd,
            ))

    def action_cancel(self) -> None:
        self.dismiss(None)