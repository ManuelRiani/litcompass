"""Vocabulary helper for the relevance filter: which words actually occur in the papers.

    python -m litcompass vocab [--from seeds|core|rejected|screened] [--contrast core|rejected] [--n 40]

Counts words and 2-3 word phrases in titles and abstracts (document frequency). With --contrast, ranks the terms
that are more frequent in the first set than in the second: `--from core --contrast rejected` suggests positive
terms, `--from rejected --contrast core` suggests negative ones. Terms should come from here, not from memory.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .config import Project
from .report import STOP
from .store import Store

EXTRA_STOP = set("""paper results show shown present presented proposed propose demonstrate demonstrated also
however used obtained respectively well both such which while has have been was were be more than due different
""".split())


def grams(text: str) -> set[str]:
    w = [t for t in re.findall(r"[a-z][a-z0-9\-]+", (text or "").lower())]
    out = set()
    for n in (1, 2, 3):
        for i in range(len(w) - n + 1):
            g = w[i:i + n]
            if g[0] in STOP or g[-1] in STOP or g[0] in EXTRA_STOP or g[-1] in EXTRA_STOP or len(g[0]) < 3:
                continue
            out.add(" ".join(g))
    return out


def docs(st: Store, which: str, seeds: set[str]) -> list[str]:
    sel = {
        "seeds": lambda d, n: d in seeds,
        "core": lambda d, n: n.get("status") == "core",
        "rejected": lambda d, n: n.get("status") == "rejected",
        "screened": lambda d, n: n.get("status") in ("core", "rejected"),
    }[which]
    return [f"{n.get('title') or ''}. {n.get('abstract') or ''}" for d, n in st.nodes.items()
            if sel(d, n) and n.get("title")]


def cmd(project: Project, a):
    cfg = project.load_config()
    st = Store.load(project.data_dir)
    seeds = {str(s["doi"]).lower() for s in cfg["seeds"]}
    A = docs(st, a.source, seeds)
    if not A:
        print(f"no papers with metadata in '{a.source}': run `python -m litcompass check --fetch` or a run first")
        return
    dfA = Counter(g for t in A for g in grams(t))
    min_df = max(2, len(A) // 50) if len(A) > 4 else 1
    if a.contrast:
        B = docs(st, a.contrast, seeds)
        dfB = Counter(g for t in B for g in grams(t))
        nB = max(len(B), 1)
        sc = {g: (c / len(A)) * math.log(((c + 0.5) / len(A)) / ((dfB[g] + 0.5) / nB))
              for g, c in dfA.items() if c >= min_df}
        print(f"# Terms over-represented in '{a.source}' ({len(A)} papers) vs '{a.contrast}' ({len(B)})\n")
        print("| term | in A | in B |\n|---|---|---|")
        for g in sorted(sc, key=lambda g: -sc[g])[:a.n]:
            print(f"| {g} | {dfA[g]} ({100 * dfA[g] / len(A):.0f}%) | {dfB[g]} ({100 * dfB[g] / nB:.0f}%) |")
    else:
        print(f"# Most frequent terms in '{a.source}' ({len(A)} papers)\n")
        print("| term | papers |\n|---|---|")
        ranked = sorted((g for g, c in dfA.items() if c >= min_df), key=lambda g: (-dfA[g], -len(g.split())))
        for g in ranked[:a.n]:
            print(f"| {g} | {dfA[g]} |")
