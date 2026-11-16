"""Re-apply the relevance filter of project.yaml to every paper already screened, with no network calls.

    python -m litcompass rescore

Use it after changing terms, weights or thresholds: recomputes scores, admitted/rejected and depth.
Newly admitted papers are expanded by the next run.
"""
from __future__ import annotations

from collections import deque

from .config import Project
from .relevance import Relevance
from .store import Store


def rescore(project: Project) -> tuple[int, int, int]:
    cfg = project.load_config()
    rel = Relevance(cfg["relevance"])
    st = Store.load(project.data_dir)
    seeds = {str(s["doi"]).lower() for s in cfg["seeds"]}
    before = {d: n.get("status") for d, n in st.nodes.items()}
    cap = int(cfg["limits"]["max_core_nodes"])

    for d, n in st.nodes.items():
        if n.get("title") is None:
            continue
        rel.rescore_node(n)
        if d in seeds:
            n.update(status="core", seed=True, depth=0)
        elif n.get("status") in ("core", "rejected"):
            n["status"] = "rejected"
    for d, n in st.nodes.items():
        if n.get("seed") and d not in seeds:
            n["seed"] = False

    n_core = sum(1 for n in st.nodes.values() if n.get("status") == "core")
    changed = True
    while changed:   # admissions by link count depend on who is already in: iterate to convergence
        changed = False
        for d, n in sorted(st.nodes.items(), key=lambda x: -st.core_links(x[0])):
            if n_core >= cap:
                break
            if n.get("status") == "rejected" and rel.admissible(n, st.core_links(d)):
                n["status"] = "core"
                n.setdefault("expanded", False)
                n_core += 1
                changed = True

    # depth = shortest distance from the seeds through admitted papers
    depth = {d: 0 for d in seeds if d in st.nodes}
    q = deque(depth)
    while q:
        d = q.popleft()
        for o in st.nbrs.get(d, ()):
            if o not in depth and st.is_core(o):
                depth[o] = depth[d] + 1
                q.append(o)
    for d, n in st.nodes.items():
        if n.get("status") == "core":
            n["depth"] = depth.get(d, n.get("depth", 1))

    st.save()
    gained = sum(1 for d, n in st.nodes.items() if n.get("status") == "core" and before.get(d) != "core")
    lost = sum(1 for d, n in st.nodes.items() if n.get("status") != "core" and before.get(d) == "core")
    return st.count("core"), gained, lost


def cmd(project: Project, args):
    core, gained, lost = rescore(project)
    st = Store.load(project.data_dir)
    print(f"rescore: {core} papers in the graph (+{gained} / -{lost}), {st.count('rejected')} rejected")
    if not args.no_report:
        from . import report
        report.build_report(project)
