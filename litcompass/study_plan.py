"""Study plan: an ordered path through the graph, from orientation to the research frontier.

    python -m litcompass study-plan [--focus REGEX] [--threads 8] [--per-thread 3] [--hide-done]

Stages (all computed from the graph, no LLM):
  1. Orientation   reviews, surveys, tutorials and book chapters with the highest centrality
  2. Foundations   the most central research papers, in chronological order
  3. Threads       for each research thread, its key papers, oldest first
  4. Frontier      recent papers already cited the most inside the graph

--focus (or study.focus in project.yaml) re-ranks everything with a PageRank personalized on the regex,
so the plan bends towards the part of the field the project cares about.
Writes reports/study_plan.md. Checkboxes follow study/progress.csv: [x] read, [~] reading, [-] skipped.
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone

from . import progress
from .config import Project, show
from .reading_list import topic_rank
from .report import load_table
from .store import Store


def fmt(r: dict, why: str, status: str | None) -> str:
    au = r["authors"].split(";")[0].strip().split()[-1] if r["authors"].strip() else "?"
    venue = f" — *{r['venue']}*" if r["venue"] else ""
    oa = f" · [open access]({r['oa_url']})" if r.get("oa_url") else ""
    year = int(float(r["year"])) if r["year"] else "n.d."
    return (f"- {progress.marker(status)} {au} ({year}). **{r['title']}**{venue}  \n"
            f"  {why} · [doi:{r['doi']}](https://doi.org/{r['doi']}){oa}")


def year(r: dict) -> int:
    return int(float(r["year"])) if r.get("year") else 0


def build_plan(project: Project, focus: str = "", threads: int = 8, per_thread: int = 3, n_orient: int = 5,
               n_found: int = 8, n_frontier: int = 6, hide_done: bool = False, include_seeds: bool = False) -> str:
    cfg = project.load_config()
    rows = load_table(project)
    if not rows:
        return "empty graph: run `python -m litcompass run` first"
    focus = focus or cfg["study"].get("focus") or ""
    score = {r["doi"]: float(r["pagerank"]) for r in rows}
    hits: dict[str, int] = {}
    if focus:
        pr, hits, _ = topic_rank(Store.load(project.data_dir), focus)
        if pr:
            score = {d: pr.get(d, 0.0) for d in score}
    rank = {d: i for i, d in enumerate(sorted(score, key=lambda d: -score[d]), 1)}
    prog = progress.load(project)
    status = {d: r["status"] for d, r in prog.items()}
    now = datetime.now(timezone.utc).year
    recent_years = int(cfg["study"]["recent_years"])

    pool = [r for r in rows if include_seeds or r["seed"] != "1"]
    if hide_done:
        pool = [r for r in pool if status.get(r["doi"]) not in ("read", "skip")]
    pool.sort(key=lambda r: -score[r["doi"]])
    used: set[str] = set()

    def why(r: dict) -> str:
        parts = [f"centrality #{rank[r['doi']]}", f"cited by {r['in_graph_citations']} graph papers"]
        if focus and r["doi"] in hits:
            parts.append("matches the focus")
        return ", ".join(parts)

    def take(cands, n):
        out = []
        for r in cands:
            if r["doi"] not in used and len(out) < n:
                out.append(r)
                used.add(r["doi"])
        return out

    # 1. orientation: top reviews/books, plus recent ones so the overview is not only historical
    overview = [r for r in pool if r.get("kind") in ("review", "book")]
    orient = take(overview, max(1, n_orient - 2))
    orient += take([r for r in overview if year(r) >= now - 8], n_orient - len(orient))
    orient += take(overview, n_orient - len(orient))
    # 2. foundations
    found = sorted(take([r for r in pool if r.get("kind", "paper") == "paper"], n_found), key=year)
    # 3. threads
    by = defaultdict(list)
    for r in pool:
        if int(r["cluster"]) > 0:
            by[int(r["cluster"])].append(r)
    weight = {k: sum(score[r["doi"]] for r in v) for k, v in by.items()}
    total = sum(weight.values()) or 1
    thread_sections = []
    for k in sorted(by, key=lambda k: -weight[k])[:threads]:
        items = sorted(take(by[k], per_thread), key=year)
        if items:
            thread_sections.append((k, items))
    # 4. frontier
    fresh = [r for r in pool if year(r) >= now - recent_years]
    fresh.sort(key=lambda r: (-int(r["in_graph_citations"] or 0), -score[r["doi"]]))
    front = take(fresh, n_frontier)

    sizes = defaultdict(int)
    spans = defaultdict(list)
    for r in rows:
        sizes[int(r["cluster"])] += 1
        if year(r):
            spans[int(r["cluster"])].append(year(r))

    title = cfg["project"].get("title") or project.slug
    L = [f"# Study plan — {title}", "",
         f"Generated {datetime.now(timezone.utc):%Y-%m-%d} from {len(rows)} papers in the citation graph."
         + (f" Focus: `/{focus}/` (personalized PageRank)." if focus else ""), "",
         "Work through the stages in order. Within each stage, items are ordered so that earlier work comes first. "
         "Mark progress with `python -m litcompass mark DOI --as read` and regenerate this file.", ""]
    if cfg["project"].get("description"):
        L += ["> " + " ".join(str(cfg["project"]["description"]).split()), ""]

    def section(name, intro, items):
        L.extend([f"## {name}", "", intro, ""])
        L.extend(fmt(r, why(r), status.get(r["doi"])) for r in items)
        if not items:
            L.append("_Nothing found in the graph for this stage._")
        L.append("")

    section("1. Orientation", "Reviews, surveys, tutorials and book chapters: read these first to get the vocabulary "
            "and the map of the field.", orient)
    section("2. Foundations", "The most central research papers of the graph, in chronological order: the results "
            "everything else builds on.", found)
    L += ["## 3. Research threads", "", "Each thread is a group of papers that cite each other and share references. "
          "Pick the threads that matter for your project; inside a thread, read in the order given.", ""]
    for k, items in thread_sections:
        label = items[0].get("cluster_label") or "—"
        sp = spans[k]
        L += [f"### Thread {k}: {label}", "",
              f"{sizes[k]} papers" + (f", {min(sp)}–{max(sp)}" if sp else "")
              + f", {100 * weight[k] / total:.0f}% of the centrality.", ""]
        L += [fmt(r, why(r), status.get(r["doi"])) for r in items]
        L.append("")
    section(f"4. Frontier (since {now - recent_years})", "Recent papers that the graph already cites the most: "
            "where the field is moving.", front)

    planned = [r["doi"] for r in orient + found + front] + [r["doi"] for _, it in thread_sections for r in it]
    n_read = sum(1 for d in planned if status.get(d) == "read")
    L += ["---", "", f"Progress: {n_read}/{len(planned)} planned papers read. "
          f"Seeds are {'included' if include_seeds else 'excluded (you chose them, so you probably know them)'}."]
    text = "\n".join(L)
    os.makedirs(project.path("reports"), exist_ok=True)
    with open(project.path("reports", "study_plan.md"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return text


def cmd(project: Project, a):
    text = build_plan(project, focus=a.focus, threads=a.threads, per_thread=a.per_thread, n_orient=a.orientation,
                      n_found=a.foundations, n_frontier=a.frontier, hide_done=a.hide_done,
                      include_seeds=a.include_seeds)
    print(text)
    print(f"\n-> {show(project.path('reports', 'study_plan.md'))}")
