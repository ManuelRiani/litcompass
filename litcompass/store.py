"""Graph state as plain text files, readable and diffable in git.

data/nodes.jsonl  one paper per line (DOI as key), sorted by DOI
data/edges.csv    citing,cited  (edges discovered while expanding graph papers)
data/runs.csv     run log

Node status: core (admitted to the graph) | candidate (discovered, not yet screened) | rejected | unresolved (no metadata)
"""
from __future__ import annotations

import csv
import json
import os
from collections import defaultdict


class Store:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.nodes: dict[str, dict] = {}
        self.edges: set[tuple[str, str]] = set()
        self.nbrs: dict[str, set[str]] = defaultdict(set)
        self.count_core = 0

    # ---------- I/O ----------
    @classmethod
    def load(cls, data_dir: str) -> "Store":
        st = cls(data_dir)
        p = os.path.join(data_dir, "nodes.jsonl")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        n = json.loads(line)
                        st.nodes[n["doi"]] = n
        p = os.path.join(data_dir, "edges.csv")
        if os.path.exists(p):
            with open(p, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    st._link(row["citing"], row["cited"])
        st.count_core = st.count("core")
        return st

    def save(self):
        os.makedirs(self.data_dir, exist_ok=True)
        tmp = os.path.join(self.data_dir, "nodes.jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for doi in sorted(self.nodes):
                f.write(json.dumps(self.nodes[doi], ensure_ascii=False, sort_keys=True) + "\n")
        os.replace(tmp, os.path.join(self.data_dir, "nodes.jsonl"))
        tmp = os.path.join(self.data_dir, "edges.csv.tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["citing", "cited"])
            w.writerows(sorted(self.edges))
        os.replace(tmp, os.path.join(self.data_dir, "edges.csv"))

    def log_run(self, row: dict):
        os.makedirs(self.data_dir, exist_ok=True)
        p = os.path.join(self.data_dir, "runs.csv")
        new = not os.path.exists(p)
        with open(p, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row), lineterminator="\n")
            if new:
                w.writeheader()
            w.writerow(row)

    def runs(self) -> list[dict]:
        p = os.path.join(self.data_dir, "runs.csv")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return list(csv.DictReader(f))

    # ---------- graph ----------
    def _link(self, citing: str, cited: str):
        self.edges.add((citing, cited))
        self.nbrs[citing].add(cited)
        self.nbrs[cited].add(citing)

    def add_edge(self, citing: str, cited: str) -> bool:
        if citing == cited or (citing, cited) in self.edges:
            return False
        self._link(citing, cited)
        return True

    def is_core(self, doi: str) -> bool:
        return self.nodes.get(doi, {}).get("status") == "core"

    def core(self) -> set[str]:
        return {d for d, n in self.nodes.items() if n.get("status") == "core"}

    def core_links(self, doi: str) -> int:
        return sum(1 for d in self.nbrs.get(doi, ()) if self.is_core(d))

    def core_depth(self, doi: str) -> int | None:
        ds = [self.nodes[d].get("depth", 0) for d in self.nbrs.get(doi, ()) if self.is_core(d)]
        return min(ds) + 1 if ds else None

    def count(self, status: str) -> int:
        return sum(1 for n in self.nodes.values() if n.get("status") == status)

    def core_digraph(self):
        import networkx as nx
        core = self.core()
        G = nx.DiGraph()
        G.add_nodes_from(core)
        G.add_edges_from((a, b) for a, b in self.edges if a in core and b in core)
        return G
