"""Offline tests: a fake citation network replaces the web sources."""
from __future__ import annotations

import os

import pytest
import yaml

from litcompass import config, progress, report, rescore, study_plan
from litcompass.relevance import Relevance
from litcompass.run import Runner
from litcompass.seeds import add_to_yaml, remove_from_yaml
from litcompass.sources import Budget, normalize_doi

REL = {"weak_cap": 3, "admit_score": 10, "admit_score_linked": 6, "admit_links_any": 5,
       "terms": {3: ["widget"], 2: ["gizmo"], 1: ["device"], -3: ["banana"]}}


class FakeHttp:
    def __init__(self):
        self.budget = Budget(10)


class FakeSources:
    """A tiny literature: s1 (seed) cites a1..a4; b1..b3 cite s1; x1 is off-topic; review r1 cites a1, a2."""

    META = {
        "10.1/s1": ("Widget theory", 2010, "article"),
        "10.1/a1": ("Early widget experiments", 1990, "article"),
        "10.1/a2": ("Gizmo widget coupling", 1995, "article"),
        "10.1/a3": ("Widget measurement methods", 2000, "article"),
        "10.1/a4": ("Banana ripening", 2001, "article"),
        "10.1/b1": ("Widget design rules", 2021, "article"),
        "10.1/b2": ("Widget arrays", 2023, "article"),
        "10.1/b3": ("A review of widget technology", 2024, "review"),
        "10.1/r1": ("Widget gizmo devices: a survey", 2015, "article"),
    }
    REFS = {"10.1/s1": ["10.1/a1", "10.1/a2", "10.1/a3", "10.1/a4"], "10.1/b1": ["10.1/a1", "10.1/a2", "10.1/s1"],
            "10.1/b2": ["10.1/a1", "10.1/b1", "10.1/s1"], "10.1/b3": ["10.1/s1", "10.1/b1", "10.1/b2", "10.1/a3"],
            "10.1/r1": ["10.1/a1", "10.1/a2"], "10.1/a2": ["10.1/a1"], "10.1/a3": ["10.1/a1", "10.1/a2"]}

    def __init__(self):
        self.http = FakeHttp()

    def references(self, doi):
        return list(self.REFS.get(doi, []))

    def citations(self, doi):
        return sorted(c for c, rs in self.REFS.items() if doi in rs)

    def metadata(self, doi):
        if doi not in self.META:
            return None
        t, y, ty = self.META[doi]
        return {"title": t, "year": y, "type": ty, "venue": "J. Widgets", "authors": ["Ann Author"], "cited_by": 10,
                "retracted": False, "abstract": "", "topic": "", "subfield": "", "oa_url": "", "openalex": "",
                "meta_src": "fake"}


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("LITCOMPASS_HOME", str(tmp_path))
    p = config.create("demo", "Demo project", "Widgets.")
    cfg = yaml.safe_load(open(p.config_path))
    cfg["seeds"] = [{"doi": "10.1/s1", "note": "seed"}]
    cfg["relevance"] = REL
    cfg["limits"]["max_depth"] = 2
    cfg["report"]["min_cluster_size"] = 2
    yaml.safe_dump(cfg, open(p.config_path, "w"))
    return p


def test_normalize_doi():
    assert normalize_doi("https://doi.org/10.1109/ABC.2020.1") == "10.1109/abc.2020.1"
    assert normalize_doi("doi:10.1234/x.") == "10.1234/x"
    assert normalize_doi("not a doi") is None


def test_relevance_title_counts_double():
    r = Relevance(REL)
    assert r.score("widget", "")[0] == 6
    assert r.score("", "widget")[0] == 3
    assert r.score("widget banana", "")[0] == 0
    assert r.score("device device", "device")[0] == 2   # weak terms count once, title double, capped at weak_cap


def test_seed_yaml_editing_keeps_comments():
    txt = "project:\n  title: x\n# keep me\nseeds: []\n\nlimits:\n  max_depth: 2\n"
    out = add_to_yaml(txt, [("10.1/a", 'say "hi"')])
    assert "# keep me" in out and yaml.safe_load(out)["seeds"] == [{"doi": "10.1/a", "note": "say 'hi'"}]
    out = add_to_yaml(out, [("10.1/b", "")])
    assert [s["doi"] for s in yaml.safe_load(out)["seeds"]] == ["10.1/a", "10.1/b"]
    out, ok = remove_from_yaml(out, "10.1/a")
    assert ok and [s["doi"] for s in yaml.safe_load(out)["seeds"]] == ["10.1/b"]
    out, ok = remove_from_yaml(out, "10.1/b")
    assert ok and yaml.safe_load(out)["seeds"] == []
    assert yaml.safe_load(out)["limits"]["max_depth"] == 2


def test_full_pipeline(project):
    reason = Runner(project, 1, sources=FakeSources()).run()
    assert reason == "complete"
    from litcompass.store import Store
    st = Store.load(project.data_dir)
    core = st.core()
    assert {"10.1/s1", "10.1/a1", "10.1/b1"} <= core
    assert "10.1/a4" not in core                      # off-topic (negative term)
    assert st.nodes["10.1/s1"]["seed"]

    assert report.build_report(project, quiet=True)
    rows = report.load_table(project)
    assert rows and {r["kind"] for r in rows} >= {"paper", "review"}

    progress.save(project, {"10.1/a1": {"doi": "10.1/a1", "status": "read", "date": "2026-01-01", "note": ""}})
    text = study_plan.build_plan(project)
    assert "## 1. Orientation" in text and "[x]" in text
    assert os.path.exists(project.path("reports", "study_plan.md"))

    # tightening the filter offline removes papers, loosening brings them back
    cfg = yaml.safe_load(open(project.config_path))
    cfg["relevance"]["admit_score"] = 99
    cfg["relevance"]["admit_score_linked"] = 99
    cfg["relevance"]["admit_links_any"] = 99
    yaml.safe_dump(cfg, open(project.config_path, "w"))
    n_core, gained, lost = rescore.rescore(project)
    assert n_core == 1 and lost > 0                   # only the seed survives


def _set_limits(project, **lim):
    cfg = yaml.safe_load(open(project.config_path))
    cfg["limits"].update(lim)
    yaml.safe_dump(cfg, open(project.config_path, "w"))


def test_no_depth_limit_saturates(project):
    _set_limits(project, max_depth=None)
    assert Runner(project, 1, sources=FakeSources()).run() == "saturated"
    from litcompass.store import Store
    st = Store.load(project.data_dir)
    waves = {w["wave"]: w for w in st.waves()}
    assert waves[0]["core"] == 1 and all(w["candidate"] == 0 for w in waves.values())
    assert "10.1/a4" not in st.core()


def test_node_cap_keeps_admissible_papers_pending(project):
    _set_limits(project, max_depth=None, max_core_nodes=3)
    assert Runner(project, 1, sources=FakeSources()).run() == "max_core_nodes"
    from litcompass.store import Store
    st = Store.load(project.data_dir)
    assert st.count("core") == 3
    # nearest wave first: everything admitted is a direct neighbour of the seed
    assert all(st.nodes[d].get("depth", 0) <= 1 for d in st.core())
    # raising the cap resumes from the pending papers
    _set_limits(project, max_core_nodes=100)
    assert Runner(project, 1, sources=FakeSources()).run() == "saturated"
    assert Store.load(project.data_dir).count("core") > 3


def test_journal_files(project):
    from litcompass import journal
    assert os.path.exists(project.path("DIARY.md")) and os.path.exists(project.path("WIP.md"))
    assert journal.open_items(project)                       # template has a first step
    with open(project.path("DIARY.md"), "a", encoding="utf-8") as f:
        f.write("\n## 2026-11-16 — first\n- Done: a\n\n## 2026-11-17 — second\n- Done: b\n")
    assert journal.last_entries(project, 1).startswith("## 2026-11-17")
    os.remove(project.path("WIP.md"))
    assert journal.ensure(project) == [project.path("WIP.md")]
