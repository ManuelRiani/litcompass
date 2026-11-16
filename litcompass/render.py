"""3D animation of the citation graph: a rotating force layout with the research threads as legend.

    python -m litcompass render [--frames 96] [--fps 10] [--labels 12] [--threads 8] [--lang en|it]

Writes reports/graph3d.gif (the rotation) and reports/graph3d.png (one still). Runs automatically at the end of
the research, when a run stops because the graph is saturated or at its size cap.

Encoding: one dot per paper, colored by research thread (the 8 largest threads get a hue, the rest are grouped as
"other"), size proportional to the citations received inside the graph; white dots = seeds; the most central papers
(PageRank) are labelled "Author Year". Thread names come from threads.yaml (`litcompass threads set`), otherwise
from their automatic terms.
"""
from __future__ import annotations

import math
import os
import time

import networkx as nx
import numpy as np

from .config import Project, show
from .report import first_author, load_table
from .store import Store

# Dark surface and categorical hues (validated 8-slot palette, dark-mode steps), never cycled: threads beyond the
# 8th fold into "other".
SURFACE = "#1a1a19"
TEXT, TEXT2, MUTED = "#f0efec", "#c3c2b7", "#8b8a83"
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"]
OTHER = "#5f5e59"
EDGE = "#8b8a83"   # darker than the white seeds, so they stand out

STRINGS = {
    "en": {"papers": "papers", "citations": "citations", "threads": "threads", "other": "other threads",
           "seed": "seed of the search", "size": "size ∝ citations received in the graph",
           "labels": "labels: top {n} by PageRank", "ungrouped": "not grouped"},
    "it": {"papers": "paper", "citations": "citazioni", "threads": "filoni", "other": "altri filoni",
           "seed": "seme della ricerca", "size": "dimensione ∝ citazioni ricevute nel grafo",
           "labels": "etichette: primi {n} per PageRank", "ungrouped": "non raggruppati"},
}


def layout3d(G: nx.DiGraph, cluster: dict[str, int], seed: int = 7) -> dict[str, np.ndarray]:
    """Force-directed layout in 3D; links inside a thread pull harder, so threads form visible clouds."""
    U = nx.Graph()
    U.add_nodes_from(G.nodes)
    for a, b in G.edges:
        same = cluster.get(a, 0) == cluster.get(b, 0) and cluster.get(a, 0) > 0
        U.add_edge(a, b, weight=3.0 if same else 1.0)
    n = max(U.number_of_nodes(), 1)
    pos = nx.spring_layout(U, dim=3, weight="weight", seed=seed, iterations=80 if n < 4000 else 50,
                           k=1.6 / math.sqrt(n))
    P = np.array([pos[d] for d in U.nodes])
    P -= np.median(P, axis=0)
    r = np.linalg.norm(P, axis=1)
    scale = np.percentile(r, 97) or 1.0
    P = P / scale
    # pull far outliers (isolated papers) back to the edge of the cloud
    r = np.linalg.norm(P, axis=1, keepdims=True)
    P = np.where(r > 1.15, P / np.maximum(r, 1e-9) * 1.15, P)
    return dict(zip(U.nodes, P))


def rotation(theta: float, tilt: float = math.radians(18)) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    ry = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    ct, st = math.cos(tilt), math.sin(tilt)
    rx = np.array([[1, 0, 0], [0, ct, -st], [0, st, ct]])
    return rx @ ry


def render(project: Project, frames: int = 96, fps: int = 10, n_labels: int = 12, max_threads: int = 8,
           lang: str = "", width: int = 900, height: int = 600, quiet: bool = False) -> str | None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from PIL import Image

    t0 = time.monotonic()
    cfg = project.load_config()
    lang = (lang or cfg["project"].get("language") or "en").lower()[:2]
    S = STRINGS.get(lang, STRINGS["en"])
    rows = load_table(project)
    if not rows:
        if not quiet:
            print("empty graph: run `python -m litcompass run` first")
        return None
    st = Store.load(project.data_dir)
    G = st.core_digraph()
    row = {r["doi"]: r for r in rows}
    cluster = {d: int(row[d]["cluster"]) if d in row else 0 for d in G.nodes}

    # threads: the largest get a hue, in fixed order; the rest fold into "other"
    sizes: dict[int, int] = {}
    for d in G.nodes:
        sizes[cluster[d]] = sizes.get(cluster[d], 0) + 1
    ranked = [k for k in sorted(sizes, key=lambda k: -sizes[k]) if k > 0]
    shown = ranked[:min(max_threads, len(SERIES))]
    color_of = {k: SERIES[i] for i, k in enumerate(shown)}
    label_of = {}
    for k in shown:
        r = next(r for r in rows if int(r["cluster"]) == k)
        name = r.get("cluster_name") or r.get("cluster_label") or f"#{k}"
        label_of[k] = name if len(name) <= 30 else name[:29].rstrip(", ") + "…"
    n_other = sum(v for k, v in sizes.items() if k not in color_of)

    nodes = list(G.nodes)
    pos = layout3d(G, cluster)
    P = np.array([pos[d] for d in nodes])
    indeg = np.array([G.in_degree(d) for d in nodes], dtype=float)
    base = 6 + 90 * np.sqrt(indeg / max(indeg.max(), 1))
    seeds = np.array([bool(st.nodes[d].get("seed")) for d in nodes])
    base[seeds] = np.maximum(base[seeds], 45)
    cols = np.array([matplotlib.colors.to_rgba(TEXT if seeds[i] else color_of.get(cluster[d], OTHER))
                     for i, d in enumerate(nodes)])
    idx = {d: i for i, d in enumerate(nodes)}
    E = np.array([(idx[a], idx[b]) for a, b in G.edges], dtype=int).reshape(-1, 2)
    edge_alpha = float(np.clip(9.0 / math.sqrt(max(len(E), 1)), 0.05, 0.3))
    pr = {r["doi"]: float(r["pagerank"]) for r in rows}
    top = [idx[d] for d in sorted(nodes, key=lambda d: -pr.get(d, 0))[:n_labels]]
    tags = [f"{first_author(st.nodes[nodes[i]])} {st.nodes[nodes[i]].get('year') or ''}".strip() for i in top]

    dpi = 100
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi, facecolor=SURFACE)
    ax = fig.add_axes([0.0, 0.0, 0.68, 1.0], facecolor=SURFACE)
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-1.2, 1.2)
    ax.set_aspect("equal")
    ax.axis("off")

    # legend panel (static)
    lg = fig.add_axes([0.68, 0.0, 0.32, 1.0], facecolor=SURFACE)
    lg.axis("off")
    lg.set_xlim(0, 1)
    lg.set_ylim(0, 1)
    title = cfg["project"].get("title") or project.slug
    lg.text(0.04, 0.955, title if len(title) <= 34 else title[:32] + "…", color=TEXT, fontsize=11.5,
            fontweight="bold", va="top")
    n_threads = len(ranked)
    lg.text(0.04, 0.905, f"{len(nodes)} {S['papers']} · {G.number_of_edges()} {S['citations']} · "
            f"{n_threads} {S['threads']}", color=TEXT2, fontsize=8.5, va="top")
    y = 0.83
    step = min(0.052, 0.62 / max(len(shown) + 2, 1))
    for k in shown:
        lg.scatter([0.065], [y], s=55, color=color_of[k], edgecolors="none")
        lg.text(0.12, y, f"{label_of[k]}  ({sizes[k]})", color=TEXT2, fontsize=8.5, va="center")
        y -= step
    if n_other:
        lg.scatter([0.065], [y], s=55, color=OTHER, edgecolors="none")
        lg.text(0.12, y, f"{S['other']}  ({n_other})", color=TEXT2, fontsize=8.5, va="center")
        y -= step
    y -= step * 0.4
    lg.scatter([0.065], [y], s=55, color=TEXT, edgecolors="none")
    lg.text(0.12, y, S["seed"], color=TEXT2, fontsize=8.5, va="center")
    lg.text(0.04, 0.075, S["size"], color=MUTED, fontsize=7.2, va="top")
    lg.text(0.04, 0.045, S["labels"].format(n=len(top)), color=MUTED, fontsize=7.2, va="top")

    lines = LineCollection([], colors=EDGE, linewidths=0.4, alpha=edge_alpha)
    ax.add_collection(lines)
    dots = ax.scatter([], [], s=[], edgecolors="none")
    texts = [ax.text(0, 0, t, color=TEXT2, fontsize=7.5, ha="center", va="bottom") for t in tags]

    D = 3.4   # camera distance
    images = []
    for f in range(frames):
        Q = P @ rotation(2 * math.pi * f / frames).T
        persp = D / (D - Q[:, 2])
        X, Y = Q[:, 0] * persp, Q[:, 1] * persp
        depth = (Q[:, 2] + 1.2) / 2.4            # 0 far .. 1 near
        order = np.argsort(Q[:, 2])                # far first
        if len(E):
            lines.set_segments(np.stack([np.c_[X[E[:, 0]], Y[E[:, 0]]], np.c_[X[E[:, 1]], Y[E[:, 1]]]], axis=1))
        c = cols.copy()
        c[:, 3] = 0.35 + 0.6 * np.clip(depth, 0, 1)
        c[seeds, 3] = 0.75 + 0.25 * np.clip(depth[seeds], 0, 1)   # seeds stay readable at the back
        dots.set_offsets(np.c_[X, Y][order])
        dots.set_sizes((base * persp ** 2)[order])
        dots.set_facecolors(c[order])
        for t, i in zip(texts, top):
            t.set_position((X[i], Y[i] + 0.035 + 0.004 * math.sqrt(base[i])))
            t.set_alpha(0.35 + 0.65 * float(np.clip(depth[i], 0, 1)))
        fig.canvas.draw()
        rgb = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
        images.append(Image.fromarray(rgb).convert("P", palette=Image.ADAPTIVE, colors=255))
    plt.close(fig)

    os.makedirs(project.path("reports"), exist_ok=True)
    out = project.path("reports", "graph3d.gif")
    images[0].save(out, save_all=True, append_images=images[1:], duration=int(1000 / fps), loop=0, disposal=2)
    images[0].convert("RGB").save(project.path("reports", "graph3d.png"))
    if not quiet:
        mb = os.path.getsize(out) / 1e6
        print(f"render: {len(nodes)} papers, {len(shown)} threads shown, {frames} frames, {mb:.1f} MB, "
              f"{time.monotonic() - t0:.0f} s -> {show(out)}")
    return out


def cmd(project: Project, a):
    render(project, frames=a.frames, fps=a.fps, n_labels=a.labels, max_threads=a.threads, lang=a.lang,
           width=a.width, height=a.height)
