"""Project journal: DIARY.md (what was done, append-only) and WIP.md (what is open, rewritten every session).

    python -m litcompass journal [--entries 1]

Prints the open items of WIP.md and the last diary entries; creates both files from the templates if missing.
Agents read it at the start of a session and update both files when the user closes the session (litcompass-close).
"""
from __future__ import annotations

import os
import re

from .config import TEMPLATE, Project, show

TEMPLATES = os.path.dirname(TEMPLATE)
FILES = ("DIARY.md", "WIP.md")


def ensure(project: Project, title: str | None = None) -> list[str]:
    """Create the missing journal files. Returns the paths created."""
    created = []
    for name in FILES:
        p = project.path(name)
        if not os.path.exists(p):
            txt = open(os.path.join(TEMPLATES, name), encoding="utf-8").read()
            with open(p, "w", encoding="utf-8") as f:
                f.write(txt.replace("__TITLE__", title or project.title))
            created.append(p)
    return created


def open_items(project: Project) -> list[str]:
    p = project.path("WIP.md")
    if not os.path.exists(p):
        return []
    return [l.strip() for l in open(p, encoding="utf-8") if re.match(r"\s*- \[ \]", l)]


def last_entries(project: Project, n: int = 1) -> str:
    p = project.path("DIARY.md")
    if not os.path.exists(p):
        return ""
    txt = re.sub(r"<!--.*?-->", "", open(p, encoding="utf-8").read(), flags=re.S)
    parts = re.split(r"(?m)^(?=## )", txt)
    entries = [x.strip() for x in parts if x.startswith("## ")]
    return "\n\n".join(entries[-n:]) if n else ""


def cmd(project: Project, a):
    for p in ensure(project):
        print(f"created {show(p)}")
    wip = project.path("WIP.md")
    print(f"# WIP — {show(wip)}\n")
    print(open(wip, encoding="utf-8").read().split("\n", 1)[1].strip())
    last = last_entries(project, a.entries)
    print(f"\n# Last diary entr{'y' if a.entries == 1 else 'ies'} — {show(project.path('DIARY.md'))}\n")
    print(last or "(no entries yet)")
