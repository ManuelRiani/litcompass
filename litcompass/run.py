"""One expansion run of the citation graph.

    python -m litcompass run [--max-minutes N] [--refresh K] [--min-age-days D]

Loop, breadth-first by waves (wave = distance from the seeds):
  1. expand every admitted paper of the nearest wave (references + citing papers from OpenCitations)
  2. screen every candidate it discovered (metadata + relevance filter), best connected first
  3. move to the next wave
Stops when time is up, when the node cap (limits.max_core_nodes) is hit, or when nothing is left to screen or expand:
"saturated", the relevance filter has closed the frontier. The optional limits.max_depth stops the expansion after a
fixed number of waves instead ("complete"); by default there is no depth limit.

--refresh K: before the loop, re-download the citing papers of the K most central graph papers whose last
refresh is older than --min-age-days. This is the maintenance mode: once the graph is complete it catches new work.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from .config import Project, depth_limit
from .relevance import SKIP_TYPES, Relevance
from .sources import Budget, Http, Sources, SourceError
from .store import Store

log = logging.getLogger("litcompass")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Runner:
    def __init__(self, project: Project, max_minutes: float | None = None, sources: Sources | None = None):
        self.project = project
        self.cfg = project.load_config()
        lim = self.cfg["limits"]
        self.max_depth = depth_limit(lim)   # None = no depth limit
        self.max_core = int(lim["max_core_nodes"])
        self.ckpt = float(lim["checkpoint_minutes"])
        self.forward_max = int(lim["forward_max_cited_by"])
        self.budget = Budget(max_minutes if max_minutes is not None else float(lim["max_minutes"]))
        self.src = sources or Sources(Http(self.budget))
        if sources is not None:
            self.src.http.budget = self.budget
        self.rel = Relevance(self.cfg["relevance"])
        self.st = Store.load(project.data_dir)
        self.stats = {"screened": 0, "admitted": 0, "rejected": 0, "expanded": 0, "refreshed": 0, "new_edges": 0}
        self.last_save = time.monotonic()

    # ---------- seeds ----------
    def init_seeds(self):
        if not self.cfg["seeds"]:
            raise SourceError("no seeds in project.yaml: add some with `python -m litcompass seeds add DOI`")
        for s in self.cfg["seeds"]:
            doi = str(s["doi"]).lower()
            n = self.st.nodes.setdefault(doi, {"doi": doi, "added": today()})
            if n.get("status") != "core":
                n.update(status="core", expanded=False)
                self.st.count_core += 1
            n.update(seed=True, depth=0, note=s.get("note", ""))
            if not n.get("title"):
                if not self.fetch_meta(n):
                    log.warning("seed %s: no metadata found (check the DOI)", doi)

    def fetch_meta(self, n: dict) -> bool:
        m = self.src.metadata(n["doi"])
        if not m:
            return False
        n.update(m)
        self.rel.rescore_node(n)
        return True

    # ---------- wave scheduling ----------
    def next_step(self) -> tuple[str | None, list[str]]:
        """Breadth-first by waves. A wave is fully expanded, then all the candidates it discovered are screened
        (best connected first), then the next wave is expanded. Returns ("expand"|"screen"|None, DOIs)."""
        exp, cands = [], []
        for doi, n in self.st.nodes.items():
            s = n.get("status")
            if s == "core" and not n.get("expanded") and \
                    (self.max_depth is None or n.get("depth", 0) < self.max_depth):
                exp.append((n.get("depth", 0), not n.get("seed"), -self.st.core_links(doi),
                            -(n.get("cited_by") or 0), doi))
            elif s == "candidate":
                links = self.st.core_links(doi)
                if links:
                    cands.append((n.get("depth", 99), -links, doi))
        d_exp = min(e[0] for e in exp) if exp else float("inf")
        d_cand = min(c[0] for c in cands) if cands else float("inf")
        if cands and d_cand <= d_exp:
            return "screen", [c[2] for c in sorted(c for c in cands if c[0] == d_cand)[:50]]
        if exp:
            return "expand", [e[4] for e in sorted(e for e in exp if e[0] == d_exp)[:10]]
        return None, []

    def screen(self, doi: str):
        n = self.st.nodes[doi]
        self.stats["screened"] += 1
        if n.get("meta_src"):          # metadata already known (e.g. held back by the node cap)
            self.rel.rescore_node(n)
        elif not self.fetch_meta(n):
            n["status"] = "unresolved"
            return
        self.decide(n)

    def decide(self, n: dict):
        if self.rel.admissible(n, self.st.core_links(n["doi"])):
            if self.st.count_core >= self.max_core:
                n["status"] = "candidate"   # admissible but over the cap: stays pending until the cap is raised
                return
            n.update(status="core", expanded=False, admitted=today(),
                     depth=self.st.core_depth(n["doi"]) or n.get("depth", 1))
            self.st.count_core += 1
            self.stats["admitted"] += 1
        else:
            n["status"] = "rejected"   # metadata and abstract stay: `rescore` needs them if the filter changes
            self.stats["rejected"] += 1

    # ---------- expansion ----------
    def wants_forward(self, n: dict) -> bool:
        """Download citing papers only for seeds and for relevant, non-hub papers."""
        return bool(n.get("seed") or (n.get("score", 0) >= self.cfg["relevance"]["admit_score_linked"]
                                      and (n.get("cited_by") or 0) <= self.forward_max))

    def _attach(self, doi: str, found: list[tuple[str, str]]):
        d = self.st.nodes[doi].get("depth", 0)
        touched = set()
        for citing, cited in found:
            other = cited if citing == doi else citing
            if self.st.add_edge(citing, cited):
                self.stats["new_edges"] += 1
            o = self.st.nodes.get(other)
            if o is None:
                self.st.nodes[other] = {"doi": other, "status": "candidate", "depth": d + 1, "added": today()}
            else:
                if o.get("status") in ("candidate", "rejected"):
                    o["depth"] = min(o.get("depth", 99), d + 1)
                touched.add(other)
        # a rejected paper that is now linked to more graph papers can come back in
        for o in touched:
            on = self.st.nodes[o]
            if on.get("status") == "rejected" and on.get("title") is not None \
                    and self.rel.admissible(on, self.st.core_links(o)):
                self.decide(on)

    def expand(self, doi: str):
        n = self.st.nodes[doi]
        found = [(doi, r) for r in self.src.references(doi)]
        forward = self.wants_forward(n)
        if forward:
            found += [(c, doi) for c in self.src.citations(doi)]
        n["forward"] = forward
        self._attach(doi, found)
        n.update(expanded=True, expanded_on=today(), n_refs=sum(1 for c, _ in found if c == doi),
                 n_cites=sum(1 for c, _ in found if c != doi))
        if forward:
            n["refreshed_on"] = today()
        self.stats["expanded"] += 1

    # ---------- maintenance ----------
    def refresh(self, k: int, min_age_days: int):
        import networkx as nx
        G = self.st.core_digraph()
        if not G.number_of_nodes():
            return
        pr = nx.pagerank(G) if G.number_of_edges() else {d: 1.0 for d in G}
        limit = (datetime.now(timezone.utc) - timedelta(days=min_age_days)).strftime("%Y-%m-%d")
        todo = [d for d in sorted(pr, key=lambda d: -pr[d])
                if self.st.nodes[d].get("expanded") and self.wants_forward(self.st.nodes[d])
                and (self.st.nodes[d].get("refreshed_on") or self.st.nodes[d].get("expanded_on") or "") <= limit][:k]
        log.info("refresh: %d papers", len(todo))
        for doi in todo:
            if self.budget.expired():
                break
            self._attach(doi, [(c, doi) for c in self.src.citations(doi)])
            self.st.nodes[doi]["refreshed_on"] = today()
            self.stats["refreshed"] += 1
            self.maybe_checkpoint()

    # ---------- loop ----------
    def maybe_checkpoint(self):
        if time.monotonic() - self.last_save > self.ckpt * 60:
            self.st.save()
            self.last_save = time.monotonic()
            log.info("checkpoint: %s | core=%d req=%d %.1f min", self.stats, self.st.count_core,
                     self.budget.requests, self.budget.elapsed_min())

    def run(self, refresh: int = 0, min_age_days: int = 30) -> str:
        # nothing left to screen or expand: "saturated" (no depth limit) or "complete" (depth limit reached)
        reason = "saturated" if self.max_depth is None else "complete"
        try:
            self.init_seeds()
            if refresh:
                self.refresh(refresh, min_age_days)
            while True:
                if self.budget.expired():
                    reason = "time"
                    break
                if self.st.count_core >= self.max_core:
                    reason = "max_core_nodes"   # candidates stay pending: raise the cap to continue
                    break
                action, dois = self.next_step()
                if action is None:
                    break
                for doi in dois:
                    if action == "screen":
                        self.screen(doi)
                    else:
                        self.expand(doi)
                    if self.budget.expired() or self.st.count_core >= self.max_core:
                        break
                self.maybe_checkpoint()
        except SourceError as e:
            log.error("run stopped: %s", e)
            reason = f"error: {e}"
        finally:
            self.st.save()
            row = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "minutes": round(self.budget.elapsed_min(), 1), "requests": self.budget.requests,
                   **self.stats, "core_total": self.st.count("core"),
                   "candidates": self.st.count("candidate"), "rejected_total": self.st.count("rejected"),
                   "edges_total": len(self.st.edges), "stop": reason}
            self.st.log_run(row)
            log.info("end of run: %s", row)
        return reason


def cmd(project: Project, args):
    reason = Runner(project, args.max_minutes).run(refresh=args.refresh, min_age_days=args.min_age_days)
    print(f"run finished: {reason}")
    if not args.no_report:
        from . import report
        report.build_report(project)
