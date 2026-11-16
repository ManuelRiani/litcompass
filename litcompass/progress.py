"""Study progress: which papers you have read, are reading, or decided to skip.

    python -m litcompass mark DOI [DOI...] --as read|reading|skip|todo [--note "..."]
    python -m litcompass progress

Stored in study/progress.csv (doi,status,date,note). Read and skipped papers leave the reading lists and the
study plan; papers being read are flagged.
"""
from __future__ import annotations

import csv
import os
from datetime import date

from .config import Project
from .sources import normalize_doi
from .store import Store

STATUSES = ("read", "reading", "skip", "todo")
FIELDS = ["doi", "status", "date", "note"]


def path(project: Project) -> str:
    return project.path("study", "progress.csv")


def load(project: Project) -> dict[str, dict]:
    p = path(project)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8", newline="") as f:
        return {r["doi"]: r for r in csv.DictReader(f)}


def save(project: Project, rows: dict[str, dict]):
    os.makedirs(os.path.dirname(path(project)), exist_ok=True)
    with open(path(project), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for doi in sorted(rows):
            w.writerow({k: rows[doi].get(k, "") for k in FIELDS})


def done(project: Project) -> set[str]:
    return {d for d, r in load(project).items() if r["status"] in ("read", "skip")}


def marker(status: str | None) -> str:
    return {"read": "[x]", "reading": "[~]", "skip": "[-]"}.get(status or "", "[ ]")


def cmd_mark(project: Project, args):
    rows = load(project)
    st = Store.load(project.data_dir)
    for raw in args.dois:
        doi = normalize_doi(raw)
        if not doi:
            print(f"not a DOI: {raw}")
            continue
        if args.status == "todo" and doi in rows and not args.note:
            del rows[doi]
            print(f"{doi}: cleared")
            continue
        rows[doi] = {"doi": doi, "status": args.status, "date": date.today().isoformat(),
                     "note": args.note or rows.get(doi, {}).get("note", "")}
        title = (st.nodes.get(doi) or {}).get("title") or "(not in the graph)"
        print(f"{doi}: {args.status} — {title[:90]}")
    save(project, rows)


def cmd_progress(project: Project, args):
    rows = load(project)
    st = Store.load(project.data_dir)
    if not rows:
        print("nothing marked yet: `python -m litcompass mark DOI --as read`")
        return
    for s in STATUSES:
        items = [r for r in rows.values() if r["status"] == s]
        if not items:
            continue
        print(f"## {s} ({len(items)})")
        for r in sorted(items, key=lambda r: r["date"], reverse=True):
            n = st.nodes.get(r["doi"]) or {}
            note = f" — {r['note']}" if r.get("note") else ""
            print(f"- {r['date']} {n.get('year') or ''} {(n.get('title') or r['doi'])[:100]}{note}")
        print()
