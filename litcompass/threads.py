"""Research threads: list them and give them human-readable names.

    python -m litcompass threads                 list threads: number, terms, size, years, top papers, name
    python -m litcompass threads set K "Name"    name thread K (written to threads.yaml in the project folder)

Thread numbers come from the clustering and can change when the graph changes, so each name is stored together with
the automatic terms of its thread and applied only while those terms still match. Names appear in the overview, the
study plan, the reading lists and the 3D animation. Agents propose names from the top papers of each thread.
"""
from __future__ import annotations

import os

import yaml

from .config import Project, show

HEADER = ("# Human-readable names of the research threads (`python -m litcompass threads`).\n"
          "# Each name is tied to the automatic terms of its thread: if the clustering changes, unmatched names are\n"
          "# ignored and the terms are shown instead.\n")


def path(project: Project) -> str:
    return project.path("threads.yaml")


def load(project: Project) -> dict[str, str]:
    """terms key -> name"""
    p = path(project)
    if not os.path.exists(p):
        return {}
    data = yaml.safe_load(open(p, encoding="utf-8")) or {}
    return {str(t.get("terms", "")).strip(): str(t.get("name", "")).strip()
            for t in data.get("threads") or [] if t.get("terms") and t.get("name")}


def save(project: Project, names: dict[str, str]):
    items = [{"terms": k, "name": v} for k, v in names.items() if v]
    with open(path(project), "w", encoding="utf-8") as f:
        f.write(HEADER)
        yaml.safe_dump({"threads": items}, f, allow_unicode=True, sort_keys=False, width=120)


def terms_key(labels: list[str]) -> str:
    return ", ".join(labels[:4])


def summary(project: Project) -> list[dict]:
    from .report import load_table
    rows = load_table(project)
    by: dict[int, list[dict]] = {}
    for r in rows:
        by.setdefault(int(r["cluster"]), []).append(r)
    out = []
    for k in sorted(by, key=lambda k: (k == 0, k)):
        items = sorted(by[k], key=lambda r: -float(r["pagerank"]))
        years = [int(float(r["year"])) for r in items if r["year"]]
        out.append({"cluster": k, "terms": items[0].get("cluster_terms", ""), "name": items[0].get("cluster_name", ""),
                    "size": len(items), "years": (min(years), max(years)) if years else None, "top": items[:5]})
    return out


def cmd(project: Project, a):
    if a.action == "set":
        th = {t["cluster"]: t for t in summary(project)}
        if a.k not in th or a.k == 0:
            raise SystemExit(f"no thread {a.k}: see `python -m litcompass threads`")
        names = load(project)
        names[th[a.k]["terms"]] = a.name
        save(project, names)
        from .report import build_report
        build_report(project, quiet=True)
        print(f"thread {a.k} ({th[a.k]['terms']}) -> {a.name}   [{show(path(project))}]")
        return
    for t in summary(project):
        head = f"## {t['cluster']}. {t['name'] or '(no name)'} — terms: {t['terms'] or '—'}" if t["cluster"] \
            else "## 0. not grouped"
        span = f", {t['years'][0]}–{t['years'][1]}" if t["years"] else ""
        print(f"{head}\n{t['size']} papers{span}")
        for r in t["top"]:
            au = r["authors"].split(";")[0].strip().split()[-1] if r["authors"].strip() else "?"
            print(f"- {au} ({r['year'] or 'n.d.'}). {r['title'][:110]} — doi:{r['doi']}")
        print()
    print('Name a thread: python -m litcompass threads set K "Name"')
