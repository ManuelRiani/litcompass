"""Project workspaces and configuration.

Every study project lives in its own folder:

    projects/<slug>/
        project.yaml        brief, seeds, relevance filter, limits   (edited by you or your agent)
        data/               nodes.jsonl, edges.csv, runs.csv          (managed by the code, never by hand)
        reports/            overview.md, study_plan.md                (generated)
        exports/            core_papers.csv, core.graphml             (generated)
        study/progress.csv  what you have read                        (via `litcompass mark`)

The projects folder can be moved elsewhere with the LITCOMPASS_HOME environment variable.
The active project is chosen, in order, by: --project, $LITCOMPASS_PROJECT, projects/.active, the only project present.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "templates", "project.yaml")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{0,63}$")

DEFAULT_LIMITS = {
    "max_minutes": 30,
    "max_core_nodes": 3000,
    "checkpoint_minutes": 5,
    "forward_max_cited_by": 3000,
}
DEFAULT_RELEVANCE = {"weak_cap": 3, "admit_score": 10, "admit_score_linked": 6, "admit_links_any": 5}
DEFAULT_REPORT = {"resolution": 1.3, "min_cluster_size": 5}
DEFAULT_STUDY = {"focus": "", "recent_years": 4}


class ConfigError(Exception):
    pass


_warned: set[str] = set()


def _warn_obsolete(slug: str, limits: dict):
    if "max_depth" in limits and slug not in _warned:
        _warned.add(slug)
        import sys
        print(f"note: limits.max_depth in {slug}/project.yaml is no longer used (the graph grows until "
              "max_core_nodes or saturation): you can delete that line", file=sys.stderr)


def projects_home() -> str:
    return os.path.abspath(os.environ.get("LITCOMPASS_HOME") or os.path.join(ROOT, "projects"))


def list_projects() -> list[str]:
    home = projects_home()
    if not os.path.isdir(home):
        return []
    return sorted(d for d in os.listdir(home)
                  if os.path.isfile(os.path.join(home, d, "project.yaml")))


def active_slug() -> str | None:
    p = os.path.join(projects_home(), ".active")
    if os.path.isfile(p):
        s = open(p, encoding="utf-8").read().strip()
        return s or None
    return None


def set_active(slug: str):
    os.makedirs(projects_home(), exist_ok=True)
    with open(os.path.join(projects_home(), ".active"), "w", encoding="utf-8") as f:
        f.write(slug + "\n")


@dataclass
class Project:
    slug: str

    @property
    def dir(self) -> str:
        return os.path.join(projects_home(), self.slug)

    def path(self, *parts: str) -> str:
        return os.path.join(self.dir, *parts)

    @property
    def config_path(self) -> str:
        return self.path("project.yaml")

    @property
    def data_dir(self) -> str:
        return self.path("data")

    def load_config(self) -> dict:
        if not os.path.isfile(self.config_path):
            raise ConfigError(f"missing {self.config_path}")
        with open(self.config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        cfg.setdefault("project", {})
        cfg["seeds"] = cfg.get("seeds") or []
        _warn_obsolete(self.slug, cfg.get("limits") or {})
        cfg["limits"] = {**DEFAULT_LIMITS, **(cfg.get("limits") or {})}
        cfg["limits"].pop("max_depth", None)
        rel = cfg.get("relevance") or {}
        cfg["relevance"] = {**DEFAULT_RELEVANCE, **rel, "terms": rel.get("terms") or {}}
        cfg["report"] = {**DEFAULT_REPORT, **(cfg.get("report") or {})}
        cfg["study"] = {**DEFAULT_STUDY, **(cfg.get("study") or {})}
        return cfg

    @property
    def title(self) -> str:
        try:
            return self.load_config()["project"].get("title") or self.slug
        except ConfigError:
            return self.slug


def resolve(slug: str | None = None) -> Project:
    slug = slug or os.environ.get("LITCOMPASS_PROJECT") or active_slug()
    if not slug:
        ps = list_projects()
        if len(ps) == 1:
            slug = ps[0]
        elif not ps:
            raise ConfigError("no project yet: create one with `python -m litcompass init <slug>`")
        else:
            raise ConfigError(f"several projects ({', '.join(ps)}): pick one with --project or `litcompass use <slug>`")
    p = Project(slug)
    if not os.path.isfile(p.config_path):
        raise ConfigError(f"project '{slug}' not found in {projects_home()}")
    return p


def create(slug: str, title: str = "", description: str = "") -> Project:
    if not SLUG_RE.match(slug):
        raise ConfigError("slug: lowercase letters, digits, '-' or '_' (max 64 chars)")
    p = Project(slug)
    if os.path.exists(p.config_path):
        raise ConfigError(f"project '{slug}' already exists")
    os.makedirs(p.dir, exist_ok=True)
    txt = open(TEMPLATE, encoding="utf-8").read()
    txt = txt.replace("__TITLE__", (title or slug).replace('"', "'"))
    desc = "\n".join("    " + line for line in (description.strip() or "TODO: describe the project").splitlines())
    txt = txt.replace("    __DESCRIPTION__", desc)
    with open(p.config_path, "w", encoding="utf-8") as f:
        f.write(txt)
    from .journal import ensure
    ensure(p, title or slug)
    return p


def show(path: str) -> str:
    """Path relative to the current folder when inside it, absolute otherwise."""
    rel = os.path.relpath(path)
    return path if rel.startswith("..") else rel
