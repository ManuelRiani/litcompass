"""Reading lists: which papers to read next.

    python -m litcompass reading-list [--n 5] [--match REGEX] [--cluster K] [--since YEAR]
    python -m litcompass reading-list --topic "REGEX" [--n 15] [--only-matching]

By thread (default): the most central papers (global PageRank) of each research thread.
By topic (--topic): personalized PageRank. Papers whose title or abstract matches the regex act as "sources" and
centrality spreads along citations, so the most important work *for that topic* surfaces, including foundational
papers that do not use the keywords.

Papers marked read or skipped (`litcompass mark`) are excluded; [~] = currently reading; OA = open-access copy known.
"""
from __future__ import annotations

import re
from collections import defaultdict

import networkx as nx

from . import progress
from .config import Project
from .report import first_author, load_table
from .store import Store


def line(au, year, title, venue, extra, doi, oa, status) -> str:
    oa_s = f" · OA: {oa}" if oa else ""
    mark = progress.marker(status) + " " if status == "reading" else ""
    return (f"{mark}{au} ({year or 'n.d.'}). {title} — *{venue}* — {extra}{oa_s} — https://doi.org/{doi}")


def by_thread(project: Project, a) -> str:
    rows = load_table(project)
    if not rows:
        return "empty graph: run `python -m litcompass run` first"
    prog = progress.load(project)
    skip = progress.done(project)
    rx = re.compile(a.match, re.I) if a.match else None
    by = defaultdict(list)
    for r in rows:
        if r["doi"] in skip or (r["seed"] == "1" and not a.include_seeds):
            continue
        if a.cluster is not None and int(r["cluster"]) != a.cluster:
            continue
        if a.since and (not r["year"] or int(float(r["year"])) < a.since):
            continue
        if rx and not rx.search(" ".join([r["title"], r.get("cluster_label", ""), r["openalex_topic"]])):
            continue
        by[int(r["cluster"])].append(r)
    out = [f"# Reading list — {project.title} ({sum(min(len(v), a.n) for v in by.values())} papers)", ""]
    for k in sorted(by, key=lambda k: -max(float(r["pagerank"]) for r in by[k])):
        items = sorted(by[k], key=lambda r: -float(r["pagerank"]))[:a.n]
        out += [f"## Thread {k}: {items[0].get('cluster_label') or '—'}" if k else "## Not yet grouped", ""]
        for r in items:
            au = r["authors"].split(";")[0].strip().split()[-1] if r["authors"].strip() else "?"
            kind = f"{r['kind']} · " if r.get("kind") and r["kind"] != "paper" else ""
            out.append("- " + line(au, r["year"], r["title"], r["venue"],
                                   f"{kind}cited by {r['in_graph_citations']} in the graph",
                                   r["doi"], r.get("oa_url"), (prog.get(r["doi"]) or {}).get("status")))
        out.append("")
    if skip:
        out.append(f"({len(skip)} papers marked read/skip excluded.)")
    return "\n".join(out)


def topic_rank(st: Store, pattern: str) -> tuple[dict[str, float], dict[str, int], nx.DiGraph]:
    rx = re.compile(pattern, re.I)
    G = st.core_digraph()
    hits = {}
    for d in G.nodes:
        n = st.nodes[d]
        h = 2 * len(rx.findall(n.get("title") or "")) + len(rx.findall(n.get("abstract") or ""))
        if h:
            hits[d] = h
    if not hits:
        return {}, {}, G
    return nx.pagerank(G, alpha=0.85, personalization=hits), hits, G


def by_topic(project: Project, a) -> str:
    st = Store.load(project.data_dir)
    pr, hits, G = topic_rank(st, a.topic)
    if not hits:
        return f"No graph paper matches /{a.topic}/ in title or abstract."
    prog = progress.load(project)
    skip = progress.done(project)
    ranked = [d for d in sorted(pr, key=lambda d: -pr[d])
              if d not in skip and (a.include_seeds or not st.nodes[d].get("seed"))
              and (not a.since or (st.nodes[d].get("year") or 0) >= a.since)
              and (not a.only_matching or d in hits)]
    n = a.n if a.n != 5 else 15
    indeg = dict(G.in_degree())
    out = [f"# Reading list for /{a.topic}/ — {project.title}", "",
           f"{len(hits)} graph papers match the topic; ranked by personalized PageRank. "
           "✓ = topic in title/abstract, ○ = central for the topic without the keywords.", ""]
    for i, d in enumerate(ranked[:n], 1):
        m = st.nodes[d]
        out.append(f"{i}. {'✓' if d in hits else '○'} " + line(
            first_author(m), m.get("year"), m.get("title"), m.get("venue", ""),
            f"cited by {indeg.get(d, 0)} in the graph", d, m.get("oa_url"), (prog.get(d) or {}).get("status")))
    read = [d for d in skip if d in hits]
    if read:
        out.append(f"\n({len(read)} papers on this topic already marked read/skip.)")
    return "\n".join(out)


def cmd(project: Project, a):
    text = by_topic(project, a) if a.topic else by_thread(project, a)
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
