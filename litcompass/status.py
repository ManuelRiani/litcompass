"""Graph status at a glance: progress, last runs, filter samples, study progress, suggested next step.

    python -m litcompass status [--samples N]
"""
from __future__ import annotations

import random

from . import progress
from .config import Project
from .store import Store


def cmd(project: Project, a):
    cfg = project.load_config()
    st = Store.load(project.data_dir)
    lim, rel = cfg["limits"], cfg["relevance"]
    core = st.count("core")
    print(f"# Status — {cfg['project'].get('title') or project.slug} ({project.slug})\n")
    print(f"- seeds: {len(cfg['seeds'])}")
    if not st.nodes:
        print("- graph: empty")
        print("\nNext: `python -m litcompass check --fetch`, then `python -m litcompass run --max-minutes 15`")
        return
    expandable = sum(1 for n in st.nodes.values()
                     if n.get("status") == "core" and not n.get("expanded") and n.get("depth", 0) < lim["max_depth"])
    links = [st.core_links(d) for d, n in st.nodes.items() if n.get("status") == "candidate"]
    linked2 = sum(1 for x in links if x >= 2)
    linked1 = sum(1 for x in links if x >= 1)
    cap = lim["max_core_nodes"]
    print(f"- in the graph: {core} / cap {cap} ({100 * core / cap:.0f}%)")
    print(f"- to expand: {expandable} | candidates waiting: {len(links)} (linked to ≥2: {linked2})")
    print(f"- rejected: {st.count('rejected')} | no metadata: {st.count('unresolved')} | edges: {len(st.edges)}")
    if core >= cap:
        phase, nxt = "stopped at max_core_nodes", "raise limits.max_core_nodes or tighten the filter, then `rescore`"
    elif expandable or linked1:
        phase, nxt = (f"building ({expandable} to expand, {linked1} candidates to screen)",
                      "`python -m litcompass run` again (each run resumes where the last one stopped)")
    else:
        phase, nxt = ("complete at max_depth", "`python -m litcompass study-plan`; later, "
                      "`python -m litcompass run --refresh 50` to catch new papers")
    print(f"- phase: {phase}")

    rows = st.runs()
    if rows:
        print("\n## Last runs\n")
        print("| date | min | requests | screened | admitted | expanded | in graph | stop |")
        print("|---|---|---|---|---|---|---|---|")
        for r in rows[-7:]:
            print(f"| {r['date'][:16]} | {r['minutes']} | {r['requests']} | {r['screened']} | {r['admitted']} | "
                  f"{r['expanded']} | {r['core_total']} | {r['stop']} |")
        errors = [r for r in rows[-7:] if r["stop"].startswith("error")]
        if errors:
            print(f"\n⚠ {len(errors)} recent run(s) ended with an error: {errors[-1]['stop']}")

    prog = progress.load(project)
    if prog:
        c = {s: sum(1 for r in prog.values() if r["status"] == s) for s in progress.STATUSES}
        print(f"\n## Study progress\n\n- read {c['read']} · reading {c['reading']} · skipped {c['skip']}")

    if a.samples:
        random.seed(0)
        last = max((n.get("admitted", "") for n in st.nodes.values()), default="")
        adm = [n for n in st.nodes.values() if n.get("status") == "core" and not n.get("seed") and n.get("admitted") == last]
        adm = adm or [n for n in st.nodes.values() if n.get("status") == "core" and not n.get("seed")]
        print(f"\n## Sample of admitted papers (latest, {last or 'n.d.'})\n")
        for n in random.sample(adm, min(a.samples, len(adm))):
            print(f"- [{n.get('score')}|{n.get('strong')}|l{st.core_links(n['doi'])}] {n.get('year')} "
                  f"{(n.get('title') or '')[:110]}")
        borderline = sorted((n for n in st.nodes.values() if n.get("status") == "rejected"),
                            key=lambda n: -(n.get("score") or 0))[:a.samples]
        print("\n## Highest-scoring rejected papers (possible false negatives)\n")
        for n in borderline:
            print(f"- [{n.get('score')}|{n.get('strong')}|l{st.core_links(n['doi'])}|{n.get('type')}] "
                  f"{(n.get('title') or '')[:110]}")
        print(f"\nLegend: [score|strong-term score|links to the graph]. Thresholds: vocabulary ≥{rel['admit_score']}, "
              f"linked ≥2 and ≥{rel['admit_score_linked']}, linked ≥{rel['admit_links_any']} and ≥0.")
    print(f"\nNext: {nxt}")
