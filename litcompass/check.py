"""Sanity check of project.yaml before (and after) running.

    python -m litcompass check [--fetch]

Validates the config (regexes, weights, thresholds, DOIs) and scores the seeds with the relevance filter:
a seed that scores below the admission threshold means the vocabulary does not describe the project yet.
--fetch downloads missing seed metadata (single lookups, free) and stores it, so the check works before any run.
"""
from __future__ import annotations

import re

from .config import Project
from .relevance import Relevance
from .run import today
from .sources import Http, Sources, normalize_doi
from .store import Store


def problems(cfg: dict) -> list[str]:
    out = []
    p = cfg["project"]
    if not p.get("description") or "TODO" in str(p.get("description")):
        out.append("project.description is empty: describe the project, agents use it to tailor advice")
    if not cfg["seeds"]:
        out.append("no seeds: find some with `seeds search` and add them with `seeds add`")
    seen = set()
    for s in cfg["seeds"]:
        d = normalize_doi(str(s.get("doi", "")))
        if not d:
            out.append(f"seed with an invalid DOI: {s.get('doi')}")
        elif d in seen:
            out.append(f"duplicate seed: {d}")
        seen.add(d)
    rel = cfg["relevance"]
    terms = rel.get("terms") or {}
    if not any(ps for ps in terms.values()):
        out.append("relevance.terms is empty: every paper would score 0 and only highly linked papers would enter")
    for w, ps in terms.items():
        try:
            int(w)
        except (TypeError, ValueError):
            out.append(f"relevance.terms: weight '{w}' is not an integer")
            continue
        for pat in ps or []:
            try:
                re.compile(pat)
            except re.error as e:
                out.append(f"invalid regex {pat!r}: {e}")
    if not any(ps for w, ps in terms.items() if str(w).lstrip("-").isdigit() and int(w) >= 2):
        out.append("no strong terms (weight >= 2): papers can only enter by links (admit_links_any)")
    if not (rel["admit_score"] >= rel["admit_score_linked"]):
        out.append("admit_score should be >= admit_score_linked")
    return out


def cmd(project: Project, a):
    cfg = project.load_config()
    issues = problems(cfg)
    print(f"# Check — {project.slug}\n")
    print("\n".join(f"- ⚠ {i}" for i in issues) if issues else "- config OK")
    if any("invalid regex" in i or "not an integer" in i for i in issues):
        return
    rel = Relevance(cfg["relevance"])
    st = Store.load(project.data_dir)
    src = Sources(Http()) if a.fetch else None
    fetched = False
    print(f"\n## Seeds scored by the filter (admission needs a strong term and score ≥ {cfg['relevance']['admit_score']})\n")
    low = 0
    for s in cfg["seeds"]:
        doi = normalize_doi(str(s.get("doi", "")))
        if not doi:
            continue
        n = st.nodes.get(doi)
        if (not n or not n.get("title")) and src:
            m = src.metadata(doi)
            if m:
                n = st.nodes.setdefault(doi, {"doi": doi, "added": today(), "status": "core", "depth": 0,
                                              "seed": True, "expanded": False})
                n.update(m)
                fetched = True
        if not n or not n.get("title"):
            print(f"- {doi}: no metadata yet (use --fetch)")
            continue
        score, strong, hits = rel.score(n.get("title", ""), n.get("abstract", ""))
        n["score"], n["strong"], n["hits"] = score, strong, hits
        ok = strong > 0 and score >= cfg["relevance"]["admit_score"]
        low += not ok
        abstract = "" if n.get("abstract") else " (no abstract: title only)"
        print(f"- {'✓' if ok else '✗'} [{score}|{strong}] {(n.get('title') or '')[:90]}{abstract}")
        print(f"    hits: {', '.join(hits) or '—'}")
    if fetched:
        st.save()
    if low:
        print(f"\n{low} seed(s) would not pass the filter on vocabulary alone. Seeds always enter, but papers like "
              "them would not: add terms (see `python -m litcompass vocab --from seeds`).")
