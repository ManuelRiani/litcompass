"""Seed papers: find them, verify them, add them to project.yaml.

    python -m litcompass seeds search "piezoelectric MEMS resonator" [--rows 20] [--since 2010] [--sort cited]
    python -m litcompass seeds add 10.1109/jmems.2009.2039697 [more DOIs...] [--note "why this seed"]
    python -m litcompass seeds list
    python -m litcompass seeds remove DOI

Search uses Crossref (free, no key). Every DOI added is verified with a single metadata lookup, so a seed
can never be a DOI that does not exist. project.yaml is edited as text: your comments are kept.
"""
from __future__ import annotations

import re

from .config import Project
from .sources import Http, Sources, normalize_doi

TOP_KEY = re.compile(r"^[A-Za-z_][\w\-]*\s*:")


def _block(lines: list[str]) -> tuple[int, int]:
    """(index of the `seeds:` line, index after the end of its block)."""
    start = next((i for i, l in enumerate(lines) if re.match(r"^seeds\s*:", l)), None)
    if start is None:
        return -1, -1
    end = start + 1
    while end < len(lines) and not TOP_KEY.match(lines[end]):
        end += 1
    return start, end


def add_to_yaml(text: str, entries: list[tuple[str, str]]) -> str:
    lines = text.splitlines()
    new = [f'  - {{doi: {doi}, note: "{note.replace(chr(34), chr(39))}"}}' for doi, note in entries]
    start, end = _block(lines)
    if start < 0:
        return text.rstrip("\n") + "\n\nseeds:\n" + "\n".join(new) + "\n"
    lines[start] = re.sub(r"\[\s*\]", "", lines[start]).rstrip()
    last = start
    for i in range(start + 1, end):
        if lines[i].strip() and not lines[i].lstrip().startswith("#"):
            last = i
    lines[last + 1:last + 1] = new
    return "\n".join(lines) + "\n"


def remove_from_yaml(text: str, doi: str) -> tuple[str, bool]:
    lines = text.splitlines()
    start, end = _block(lines)
    if start < 0:
        return text, False
    rx = re.compile(r"^\s*-\s*\{?\s*doi:\s*['\"]?" + re.escape(doi) + r"['\"]?\s*[,}]?", re.I)
    keep = [l for i, l in enumerate(lines) if not (start < i < end and rx.match(l))]
    if len(keep) == len(lines):
        return text, False
    _, end2 = _block(keep)
    if not any(l.strip().startswith("-") for l in keep[start + 1:end2]):
        keep[start] = "seeds: []"
    return "\n".join(keep) + "\n", True


def cmd_search(a):
    src = Sources(Http())
    res = src.search(a.query, rows=a.rows, since=a.since, until=a.until)
    if a.sort == "cited":
        res.sort(key=lambda r: -(r.get("cited_by") or 0))
    if not res:
        print("no results")
        return
    print(f"# Crossref results for: {a.query}\n")
    print("| # | DOI | year | cited by | type | first author | title | venue |")
    print("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(res, 1):
        au = r["authors"][0].split()[-1] if r["authors"] and r["authors"][0].split() else "?"
        t = (r["title"] or "").replace("|", "/")[:110]
        v = (r["venue"] or "").replace("|", "/")[:40]
        print(f"| {i} | {r['doi']} | {r['year'] or ''} | {r['cited_by']} | {r['type'] or ''} | {au} | {t} | {v} |")
    print("\nAdd the right ones with: python -m litcompass seeds add DOI [DOI...] --note \"why\"")


def cmd_add(project: Project, a):
    cfg = project.load_config()
    have = {str(s["doi"]).lower() for s in cfg["seeds"]}
    src = Sources(Http())
    entries = []
    for raw in a.dois:
        doi = normalize_doi(raw)
        if not doi:
            print(f"skip: not a DOI: {raw}")
            continue
        if doi in have:
            print(f"skip: already a seed: {doi}")
            continue
        note = a.note or ""
        if not a.no_verify:
            m = src.metadata(doi)
            if not m:
                print(f"skip: DOI not found in OpenAlex or Crossref: {doi}")
                continue
            au = m["authors"][0].split()[-1] if m["authors"] and m["authors"][0].split() else "?"
            label = f"{au} {m.get('year') or ''}: {m.get('title') or ''}"[:140]
            note = note or label
            print(f"ok: {doi} — {label}")
        entries.append((doi, note))
        have.add(doi)
    if entries:
        with open(project.config_path, encoding="utf-8") as f:
            text = f.read()
        with open(project.config_path, "w", encoding="utf-8") as f:
            f.write(add_to_yaml(text, entries))
        print(f"{len(entries)} seed(s) added to {project.config_path}")


def cmd_remove(project: Project, a):
    doi = normalize_doi(a.doi) or a.doi.lower()
    with open(project.config_path, encoding="utf-8") as f:
        text, ok = remove_from_yaml(f.read(), doi)
    if ok:
        with open(project.config_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"removed {doi}; run `python -m litcompass rescore` to update the graph")
    else:
        print(f"{doi} is not a seed (or is written in a format this command does not recognise: edit project.yaml)")


def cmd_list(project: Project, a):
    cfg = project.load_config()
    from .store import Store
    st = Store.load(project.data_dir)
    if not cfg["seeds"]:
        print("no seeds yet")
    for s in cfg["seeds"]:
        doi = str(s["doi"]).lower()
        n = st.nodes.get(doi) or {}
        info = f"{n.get('year') or ''} {n.get('title') or '(metadata not fetched yet)'}"[:110]
        print(f"- {doi} — {info} — {s.get('note', '')}")
