"""Map of the graph: paper importance and research threads, graph math only (no LLM).

    python -m litcompass report

Writes, inside the project folder:
  reports/overview.md      readable overview: stats, foundational papers, recent work, threads
  exports/core_papers.csv  table of admitted papers with cluster and scores (input for reading lists and study plan)
  exports/core.graphml     graph of admitted papers (Gephi, Cytoscape, networkx...)
"""
from __future__ import annotations

import csv
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

import networkx as nx

from .config import Project, show
from .store import Store

STOP = set("""a an and are as at based by for from in into is of on or the to with via using use its their this
that these new novel study analysis design high low over under between toward towards approach method methods
investigation characterization performance application applications device devices system systems effect effects
through within without non two three one first second all can not how what why when does do our we vs versus
""".split())
MAX_GROUP = 60   # references/citing papers shared by more than N papers do not count for similarity (too generic)
REVIEW_RX = re.compile(r"\b(review|survey|tutorial|overview|primer|state[- ]of[- ]the[- ]art|progress in|perspectives?|"
                       r"roadmap|introduction to|lecture notes|handbook|textbook)\b", re.I)
BOOK_TYPES = {"book", "book-chapter", "monograph", "edited-book", "reference-book", "reference-entry", "book-part"}


def tokens(title: str) -> list[str]:
    w = [t for t in re.findall(r"[a-z0-9][a-z0-9\-]+", (title or "").lower()) if t not in STOP and not t.isdigit()]
    return w + [f"{a} {b}" for a, b in zip(w, w[1:])]


def kind(n: dict) -> str:
    """review | book | paper"""
    if n.get("type") == "review" or REVIEW_RX.search(n.get("title") or ""):
        return "review"
    if n.get("type") in BOOK_TYPES:
        return "book"
    return "paper"


def first_author(n: dict) -> str:
    a = n.get("authors") or []
    return a[0].split()[-1] if a and a[0].split() else "?"


def cite(n: dict, doi: str) -> str:
    venue = f" — *{n['venue']}*" if n.get("venue") else ""
    return f"{first_author(n)} ({n.get('year') or 'n.d.'}). {n.get('title') or doi}{venue}. [doi:{doi}](https://doi.org/{doi})"


def similarity_graph(st: Store, core: set[str], G: nx.DiGraph) -> nx.Graph:
    """Direct citation + bibliographic coupling + co-citation."""
    U = nx.Graph()
    U.add_nodes_from(core)
    for a, b in G.edges:
        U.add_edge(a, b, weight=U.get_edge_data(a, b, {"weight": 0})["weight"] + 1.0)
    cited_by_core, citing_core = defaultdict(list), defaultdict(list)
    for a, b in st.edges:
        if a in core:
            cited_by_core[b].append(a)
        if b in core:
            citing_core[a].append(b)
    for group in list(cited_by_core.values()) + list(citing_core.values()):
        g = sorted(set(group))
        if 2 <= len(g) <= MAX_GROUP:
            w = 1.0 / (len(g) - 1)
            for i in range(len(g)):
                for j in range(i + 1, len(g)):
                    e = U.get_edge_data(g[i], g[j])
                    U.add_edge(g[i], g[j], weight=(e["weight"] if e else 0) + w)
    return U


def cluster_labels(st: Store, core: set[str], cluster: dict[str, int], extra_generic: set[str]) -> dict[int, list[str]]:
    tf = defaultdict(Counter)
    for d in core:
        tf[cluster[d]].update(set(tokens(st.nodes[d].get("title", ""))))
    total = Counter()
    for c in tf.values():
        total.update(c)
    # words in more than 30% of all titles say nothing about a single thread
    generic = {t for t, n in total.items() if n > 0.3 * len(core)} | extra_generic
    sizes = Counter(cluster[d] for d in core)
    labels = {}
    for k, c in tf.items():
        size, rest = sizes[k], max(len(core) - sizes[k], 1)
        sc = {}
        for t, n in c.items():
            if n < max(2, min(3, size // 4)) or t in generic:
                continue
            p_in = n / size
            p_out = (total[t] - n + 0.5) / rest
            sc[t] = p_in * math.log(p_in / p_out)
        out = []
        for t in sorted(sc, key=lambda t: -sc[t]):   # avoid near-duplicates such as "thin" + "thin films"
            if any(t in o or o in t for o in out):
                continue
            out.append(t)
            if len(out) == 6:
                break
        labels[k] = out
    return labels


def build_report(project: Project, quiet: bool = False) -> str | None:
    cfg = project.load_config()
    st = Store.load(project.data_dir)
    core = st.core()
    if not core:
        if not quiet:
            print("empty graph: run `python -m litcompass run` first")
        return None
    G = st.core_digraph()
    U = similarity_graph(st, core, G)
    pr = nx.pagerank(G, alpha=0.85) if G.number_of_edges() else {d: 1 / len(core) for d in core}
    indeg = dict(G.in_degree())

    rcfg = cfg["report"]
    comms = nx.community.louvain_communities(U, weight="weight", resolution=float(rcfg["resolution"]), seed=42)
    comms = sorted(comms, key=lambda c: -sum(pr[d] for d in c))
    big = [c for c in comms if len(c) >= int(rcfg["min_cluster_size"])]
    cluster = {d: i for i, c in enumerate(big, 1) for d in c}
    for d in core:
        cluster.setdefault(d, 0)   # 0 = small groups / not linked
    labels = cluster_labels(st, core, cluster, {t.lower() for t in rcfg.get("generic_terms") or []})
    topics = defaultdict(Counter)
    for d in core:
        if st.nodes[d].get("topic"):
            topics[cluster[d]][st.nodes[d]["topic"]] += 1

    # ---------- exports ----------
    os.makedirs(project.path("exports"), exist_ok=True)
    os.makedirs(project.path("reports"), exist_ok=True)
    with open(project.path("exports", "core_papers.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["doi", "title", "year", "venue", "authors", "kind", "type", "cluster", "cluster_label", "pagerank",
                    "in_graph_citations", "cited_by_global", "depth", "seed", "relevance_score", "openalex_topic",
                    "oa_url"])
        for d in sorted(core, key=lambda d: -pr[d]):
            n = st.nodes[d]
            w.writerow([d, n.get("title", ""), n.get("year", ""), n.get("venue", ""), "; ".join(n.get("authors") or []),
                        kind(n), n.get("type", ""), cluster[d], ", ".join(labels.get(cluster[d], [])[:4]),
                        f"{pr[d]:.6f}", indeg.get(d, 0), n.get("cited_by", 0), n.get("depth", ""),
                        int(bool(n.get("seed"))), n.get("score", ""), n.get("topic", ""), n.get("oa_url", "")])
    for d in G.nodes:
        n = st.nodes[d]
        G.nodes[d].update(title=n.get("title") or "", year=int(n.get("year") or 0), cluster=cluster[d],
                          pagerank=float(pr[d]), seed=bool(n.get("seed")), kind=kind(n))
    nx.write_graphml(G, project.path("exports", "core.graphml"))

    # ---------- overview.md ----------
    L = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    expanded = sum(1 for d in core if st.nodes[d].get("expanded"))
    L += [f"# Literature map — {cfg['project'].get('title') or project.slug}", "", f"Updated: {ts}", "",
          "| | |", "|---|---|",
          f"| Papers in the graph | {len(core)} |",
          f"| of which expanded (references + citing papers downloaded) | {expanded} |",
          f"| Candidates waiting for screening | {st.count('candidate')} |",
          f"| Rejected by the relevance filter | {st.count('rejected')} |",
          f"| Citations inside the graph | {G.number_of_edges()} |",
          f"| Research threads (clusters ≥ {rcfg['min_cluster_size']} papers) | {len(big)} |", ""]
    waves = st.waves()
    L += ["Papers per wave (distance from the seeds), with the share of screened papers admitted: "
          + ", ".join(f"wave {w['wave']}: {w['core']}" + (f" ({100 * w['rate']:.0f}%)" if w["rate"] is not None and w["wave"] else "")
                      for w in waves if w["core"]), ""]

    L += ["## Foundational papers", "",
          "Sorted by PageRank on the internal graph: being cited by papers that are themselves central weighs more.", ""]
    for i, d in enumerate(sorted(core, key=lambda d: -pr[d])[:30], 1):
        tag = " · **seed**" if st.nodes[d].get("seed") else ""
        L.append(f"{i}. {cite(st.nodes[d], d)} — cited by {indeg.get(d, 0)} graph papers{tag}")
    L.append("")

    yr = datetime.now(timezone.utc).year
    ry = int(cfg["study"]["recent_years"])
    recent = [d for d in core if (st.nodes[d].get("year") or 0) >= yr - ry]
    if recent:
        L += [f"## Most cited recent work (since {yr - ry})", ""]
        for d in sorted(recent, key=lambda d: (-indeg.get(d, 0), -(st.nodes[d].get("cited_by") or 0)))[:15]:
            L.append(f"- {cite(st.nodes[d], d)} — {indeg.get(d, 0)} in the graph, {st.nodes[d].get('cited_by', 0)} overall")
        L.append("")

    L += ["## Research threads", "",
          "Louvain clustering on direct citations, shared references and co-citations. Labels are the most "
          "distinctive title terms of each group; numbering can change between runs.", ""]
    for k in list(range(1, len(big) + 1)) + ([0] if any(cluster[d] == 0 for d in core) else []):
        members = sorted((d for d in core if cluster[d] == k), key=lambda d: -pr[d])
        if not members:
            continue
        name = ", ".join(labels.get(k, [])[:5]) or "—"
        L += [f"### {k}. {name}" if k else "### Not yet grouped", ""]
        yrs = [st.nodes[d].get("year") for d in members if st.nodes[d].get("year")]
        L.append(f"{len(members)} papers" + (f", {min(yrs)}–{max(yrs)}" if yrs else "") + ".")
        if topics.get(k):
            L.append("Main OpenAlex topics: " + "; ".join(f"{t} ({n})" for t, n in topics[k].most_common(3)) + ".")
        L.append("")
        L += [f"- {cite(st.nodes[d], d)}" for d in members[:8]]
        L.append("")

    rows = st.runs()[-5:]
    if rows:
        L += ["## Last runs", "", "| date | min | requests | screened | admitted | expanded | stop |",
              "|---|---|---|---|---|---|---|"]
        for r in rows:
            L.append(f"| {r['date'][:16]} | {r['minutes']} | {r['requests']} | {r['screened']} | {r['admitted']} | "
                     f"{r['expanded']} | {r['stop']} |")
        L.append("")

    out = project.path("reports", "overview.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    if not quiet:
        print(f"report: {len(core)} papers, {len(big)} threads -> {show(out)}")
    return out


def load_table(project: Project) -> list[dict]:
    """exports/core_papers.csv, regenerated if missing or older than the graph data."""
    p = project.path("exports", "core_papers.csv")
    nodes = os.path.join(project.data_dir, "nodes.jsonl")
    if not os.path.exists(p) or (os.path.exists(nodes) and os.path.getmtime(nodes) > os.path.getmtime(p)):
        build_report(project, quiet=True)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cmd(project: Project, args):
    build_report(project)
