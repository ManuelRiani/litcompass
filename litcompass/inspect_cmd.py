"""Look inside the graph without loading big files: one paper, or a local search.

    python -m litcompass paper DOI            metadata, abstract, thread, citations inside the graph
    python -m litcompass find REGEX [--all]   graph papers whose title/abstract match (--all: also rejected ones)

Meant for agents too: these outputs are the sources to quote, with the DOI.
"""
from __future__ import annotations

import re

from . import progress
from .config import Project
from .report import first_author, kind, load_table
from .sources import normalize_doi
from .store import Store


def _short(n: dict, doi: str) -> str:
    return f"{first_author(n)} ({n.get('year') or 'n.d.'}). {(n.get('title') or doi)[:100]} — doi:{doi}"


def cmd_paper(project: Project, a):
    st = Store.load(project.data_dir)
    doi = normalize_doi(a.doi) or a.doi.lower()
    n = st.nodes.get(doi)
    if not n:
        print(f"{doi} is not in this project's data")
        return
    row = next((r for r in load_table(project) if r["doi"] == doi), None)
    status = (progress.load(project).get(doi) or {}).get("status", "")
    print(f"# {n.get('title') or doi}\n")
    print(f"- authors: {', '.join(n.get('authors') or []) or '?'}")
    print(f"- year: {n.get('year') or 'n.d.'} · venue: {n.get('venue') or '—'} · type: {n.get('type') or '?'} ({kind(n)})")
    print(f"- doi: https://doi.org/{doi}" + (f" · open access: {n['oa_url']}" if n.get("oa_url") else ""))
    print(f"- graph status: {n.get('status')}" + (" · seed" if n.get("seed") else "")
          + f" · relevance score {n.get('score')} · cited by {n.get('cited_by', 0)} overall")
    if row:
        print(f"- thread {row['cluster']}: {row['cluster_label'] or '—'} · pagerank {row['pagerank']} · "
              f"cited by {row['in_graph_citations']} graph papers")
    if n.get("topic"):
        print(f"- OpenAlex topic: {n['topic']}")
    if status:
        print(f"- your progress: {status}")
    print(f"\n## Abstract\n\n{n.get('abstract') or '(no abstract available from the free sources)'}")
    refs = [c for (a_, c) in st.edges if a_ == doi and st.is_core(c)]
    cits = [c for (c, b) in st.edges if b == doi and st.is_core(c)]
    for name, lst in (("Cites (in the graph)", refs), ("Cited by (in the graph)", cits)):
        if lst:
            print(f"\n## {name}: {len(lst)}\n")
            for d in sorted(lst, key=lambda d: -(st.nodes[d].get("year") or 0))[:a.max]:
                print(f"- {_short(st.nodes[d], d)}")


def cmd_find(project: Project, a):
    st = Store.load(project.data_dir)
    rx = re.compile(a.regex, re.I)
    out = []
    for d, n in st.nodes.items():
        if n.get("status") != "core" and not (a.all and n.get("status") == "rejected"):
            continue
        t, ab = n.get("title") or "", n.get("abstract") or ""
        h = 2 * len(rx.findall(t)) + len(rx.findall(ab))
        if h:
            out.append((h, n.get("cited_by") or 0, d))
    out.sort(reverse=True)
    print(f"{len(out)} papers match /{a.regex}/" + (" (graph + rejected)" if a.all else " in the graph"))
    for h, _, d in out[:a.n]:
        n = st.nodes[d]
        flag = "" if n.get("status") == "core" else " [rejected]"
        print(f"- {_short(n, d)}{flag}")
