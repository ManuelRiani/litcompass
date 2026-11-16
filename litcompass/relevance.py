"""Deterministic relevance filter (no LLM): weighted regex terms on title and abstract, plus graph links."""
from __future__ import annotations

import re

SKIP_TYPES = {"paratext", "erratum", "retraction", "peer-review", "grant", "dataset",
              "supplementary-materials", "component", "editorial", "letter"}


class Relevance:
    """Score = sum of the weights of the terms found. A term in the title counts double.

    Terms with weight 1 contribute at most `weak_cap` points. Negative weights push out off-topic papers.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.weak_cap = int(cfg.get("weak_cap", 3))
        self.terms: list[tuple[int, re.Pattern]] = []
        for w, ps in (cfg.get("terms") or {}).items():
            for p in ps or []:
                self.terms.append((int(w), re.compile(p, re.I)))

    def score(self, title: str, abstract: str) -> tuple[int, int, list[str]]:
        """-> (total score, score of strong terms only (weight >= 2), matched patterns)"""
        strong = weak = neg = 0
        hits = []
        for w, rx in self.terms:
            m = 2 if rx.search(title or "") else (1 if rx.search(abstract or "") else 0)
            if not m:
                continue
            hits.append(rx.pattern)
            if w >= 2:
                strong += w * m
            elif w == 1:
                weak += m
            else:
                neg += w * m
        return strong + min(weak, self.weak_cap) + neg, strong, hits

    def admit(self, score: int, strong: int, links: int) -> bool:
        c = self.cfg
        return ((strong > 0 and score >= c["admit_score"])
                or (links >= 2 and strong > 0 and score >= c["admit_score_linked"])
                or (links >= c["admit_links_any"] and score >= 0))

    def admissible(self, node: dict, links: int) -> bool:
        return (node.get("type") not in SKIP_TYPES and not node.get("retracted")
                and self.admit(node.get("score", 0), node.get("strong", 0), links))

    def rescore_node(self, n: dict):
        n["score"], n["strong"], n["hits"] = self.score(n.get("title", ""), n.get("abstract", ""))
