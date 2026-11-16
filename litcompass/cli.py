"""Command line: python -m litcompass <command> [options]   (or `litcompass <command>` once pip-installed)."""
from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
from . import (check, inspect_cmd, journal, progress, reading_list, render, report, rescore, run, seeds, status,
               study_plan, threads, vocab)
from .config import ConfigError, create, list_projects, active_slug, resolve, set_active
from .sources import SourceError


def _use_system_certificates():
    """Trust the operating system's certificate store (corporate proxies that inspect HTTPS)."""
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:   # not installed or not supported: fall back to certifi
        pass


def _init(a):
    p = create(a.slug, a.title or "", a.description or "")
    set_active(a.slug)
    print(f"created {p.config_path} (now the active project)")
    print("Next: describe the project in project.yaml, then `python -m litcompass seeds search \"...\"`")


def _use(a):
    resolve(a.slug)
    set_active(a.slug)
    print(f"active project: {a.slug}")


def _projects(a):
    act = active_slug()
    ps = list_projects()
    if not ps:
        print("no projects yet: `python -m litcompass init <slug>`")
    for s in ps:
        print(("* " if s == act else "  ") + s)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="litcompass", description=__doc__)
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("-p", "--project", help="project slug (default: active project)")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="command")

    s = sub.add_parser("init", help="create a new project")
    s.add_argument("slug")
    s.add_argument("--title")
    s.add_argument("--description")
    s.set_defaults(fn=_init, needs_project=False)

    s = sub.add_parser("use", help="set the active project")
    s.add_argument("slug")
    s.set_defaults(fn=_use, needs_project=False)

    s = sub.add_parser("projects", help="list projects")
    s.set_defaults(fn=_projects, needs_project=False)

    s = sub.add_parser("seeds", help="search, add, list or remove seed papers")
    ss = s.add_subparsers(dest="seeds_cmd", required=True, metavar="action")
    x = ss.add_parser("search", help="keyword search on Crossref")
    x.add_argument("query")
    x.add_argument("--rows", type=int, default=20)
    x.add_argument("--since", type=int)
    x.add_argument("--until", type=int)
    x.add_argument("--sort", choices=["relevance", "cited"], default="relevance")
    x.set_defaults(fn=seeds.cmd_search, needs_project=False)
    x = ss.add_parser("add", help="verify and add DOIs to project.yaml")
    x.add_argument("dois", nargs="+")
    x.add_argument("--note", default="")
    x.add_argument("--no-verify", action="store_true")
    x.set_defaults(fn=seeds.cmd_add)
    x = ss.add_parser("list")
    x.set_defaults(fn=seeds.cmd_list)
    x = ss.add_parser("remove")
    x.add_argument("doi")
    x.set_defaults(fn=seeds.cmd_remove)

    s = sub.add_parser("check", help="validate project.yaml and score the seeds")
    s.add_argument("--fetch", action="store_true", help="download missing seed metadata (free lookups)")
    s.set_defaults(fn=check.cmd)

    s = sub.add_parser("vocab", help="frequent / distinctive terms, to build the relevance filter")
    s.add_argument("--from", dest="source", choices=["seeds", "core", "rejected", "screened"], default="seeds")
    s.add_argument("--contrast", choices=["core", "rejected", "screened"])
    s.add_argument("--n", type=int, default=40)
    s.set_defaults(fn=vocab.cmd)

    s = sub.add_parser("run", help="expand the graph (network)")
    s.add_argument("--max-minutes", type=float)
    s.add_argument("--refresh", type=int, default=0, metavar="K",
                   help="first re-download the citing papers of the K most central papers (maintenance)")
    s.add_argument("--min-age-days", type=int, default=30)
    s.add_argument("--no-report", action="store_true")
    s.add_argument("--no-render", action="store_true", help="skip the 3D animation when the graph is finished")
    s.set_defaults(fn=run.cmd)

    s = sub.add_parser("rescore", help="re-apply the relevance filter offline")
    s.add_argument("--no-report", action="store_true")
    s.set_defaults(fn=rescore.cmd)

    s = sub.add_parser("report", help="rebuild overview.md and exports")
    s.set_defaults(fn=report.cmd)

    s = sub.add_parser("threads", help="list the research threads, or name one: threads set K \"Name\"")
    s.add_argument("action", nargs="?", choices=["list", "set"], default="list")
    s.add_argument("k", nargs="?", type=int)
    s.add_argument("name", nargs="?")
    s.set_defaults(fn=threads.cmd)

    s = sub.add_parser("render", help="3D rotating animation of the graph -> reports/graph3d.gif")
    s.add_argument("--frames", type=int, default=96, help="frames per full turn (more = slower, smoother)")
    s.add_argument("--fps", type=int, default=10)
    s.add_argument("--labels", type=int, default=12, help="papers labelled 'Author Year' (top PageRank)")
    s.add_argument("--threads", type=int, default=8, help="threads with their own color (max 8)")
    s.add_argument("--lang", default="", help="legend language: en, it (default: project.language)")
    s.add_argument("--width", type=int, default=900)
    s.add_argument("--height", type=int, default=600)
    s.set_defaults(fn=render.cmd)

    s = sub.add_parser("status", help="graph status and next step")
    s.add_argument("--samples", type=int, default=0)
    s.set_defaults(fn=status.cmd)

    s = sub.add_parser("reading-list", help="what to read next, by thread or by topic")
    s.add_argument("--n", type=int, default=5)
    s.add_argument("--match", default="")
    s.add_argument("--cluster", type=int)
    s.add_argument("--since", type=int, default=0)
    s.add_argument("--topic", default="")
    s.add_argument("--only-matching", action="store_true")
    s.add_argument("--include-seeds", action="store_true")
    s.add_argument("--out")
    s.set_defaults(fn=reading_list.cmd)

    s = sub.add_parser("study-plan", help="ordered study path -> reports/study_plan.md")
    s.add_argument("--focus", default="")
    s.add_argument("--threads", type=int, default=8)
    s.add_argument("--per-thread", type=int, default=3)
    s.add_argument("--orientation", type=int, default=5)
    s.add_argument("--foundations", type=int, default=8)
    s.add_argument("--frontier", type=int, default=6)
    s.add_argument("--hide-done", action="store_true")
    s.add_argument("--include-seeds", action="store_true")
    s.set_defaults(fn=study_plan.cmd)

    s = sub.add_parser("paper", help="one paper: metadata, abstract, citations in the graph")
    s.add_argument("doi")
    s.add_argument("--max", type=int, default=15)
    s.set_defaults(fn=inspect_cmd.cmd_paper)

    s = sub.add_parser("find", help="search titles and abstracts of the graph (regex)")
    s.add_argument("regex")
    s.add_argument("--n", type=int, default=30)
    s.add_argument("--all", action="store_true", help="include rejected papers")
    s.set_defaults(fn=inspect_cmd.cmd_find)

    s = sub.add_parser("mark", help="record reading progress")
    s.add_argument("dois", nargs="+")
    s.add_argument("--as", dest="status", choices=progress.STATUSES, default="read")
    s.add_argument("--note", default="")
    s.set_defaults(fn=progress.cmd_mark)

    s = sub.add_parser("journal", help="open items of WIP.md and last DIARY.md entries")
    s.add_argument("--entries", type=int, default=1)
    s.set_defaults(fn=journal.cmd)

    s = sub.add_parser("progress", help="show reading progress")
    s.set_defaults(fn=progress.cmd_progress)
    return ap


def main(argv: list[str] | None = None):
    for stream in (sys.stdout, sys.stderr):   # Windows consoles: avoid UnicodeEncodeError on ✓, —, …
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    _use_system_certificates()
    a = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if (a.verbose or a.cmd == "run") else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        if getattr(a, "needs_project", True):
            a.fn(resolve(a.project), a)
        else:
            a.fn(a)
    except ConfigError as e:
        sys.exit(f"error: {e}")
    except SourceError as e:
        hint = ""
        if "certificate" in str(e).lower() or "ssl" in str(e).lower():
            hint = "\nhint: a proxy inspects HTTPS: `python -m pip install --user truststore` and retry"
        sys.exit(f"network error: {e}{hint}")


if __name__ == "__main__":
    main()
