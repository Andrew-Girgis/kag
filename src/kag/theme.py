from __future__ import annotations

from textual.theme import BUILTIN_THEMES

TERMINAL = "terminal"
KAG = "kag"
DEFAULT_THEME = TERMINAL
ALIASES = {TERMINAL: "textual-ansi", KAG: "textual-dark"}
LABELS = {textual_name: name for name, textual_name in ALIASES.items()}


def theme_names() -> list[str]:
    others = sorted(name for name in BUILTIN_THEMES if name not in LABELS)
    return [TERMINAL, KAG, *others]


def theme_label(textual_name: str) -> str:
    return LABELS.get(textual_name, textual_name)


def resolve_theme(name: str) -> tuple[str, str | None]:
    normalized = name.strip().lower()
    if normalized in ALIASES:
        return ALIASES[normalized], None
    if normalized in BUILTIN_THEMES:
        return normalized, None
    choices = ", ".join(theme_names())
    warning = f"unknown theme {name!r}; using {DEFAULT_THEME}. Choices: {choices}"
    return ALIASES[DEFAULT_THEME], warning
