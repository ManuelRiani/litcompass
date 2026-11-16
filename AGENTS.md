# Instructions for AI coding agents (Claude Code, GitHub Copilot, others)

This repository is **litcompass**: it builds a citation graph of the scientific literature around the user's
project and turns it into reading lists and a study plan. The code does the mechanical work (free bibliographic
APIs, graph math, deterministic filter). You, the agent, do the conversation: understand the project, help choose
seeds and vocabulary, tune the filter with the user, and turn the plan into study advice.

Reply in the user's language. Keep code, file contents and commit messages in English.

## Workflows (skills)

The procedures live in `.claude/skills/<name>/SKILL.md`. Claude Code and GitHub Copilot (VS Code agent mode,
Copilot CLI, coding agent) both load skills from that folder; in VS Code the same procedures are also available as
prompt files in `.github/prompts/`. If your tool cannot load skills, open the SKILL.md and follow it.

| Skill | Use it when |
|---|---|
| `litcompass-setup` | The user starts a new project: brief → seeds → vocabulary → pilot run. |
| `litcompass-build` | Growing or maintaining a graph: runs, status, filter tuning, refresh, caps. |
| `litcompass-study` | The graph exists: study plan, reading lists, study advice, questions about the literature. |
| `litcompass-close` | The user wants to close the chat/session: update DIARY.md, rewrite WIP.md for the next chat. |

## Sessions: start and close

Each project keeps a journal: `DIARY.md` (what was done, append-only) and `WIP.md` (what is open).

- **Start of a session**: run `python -m litcompass projects`, `python -m litcompass status` and
  `python -m litcompass journal`, then propose the step under "Next session starts with" in WIP.md (or, if there is
  none, the next step printed by `status`).
- **Close of a session**: whenever the user says they want to close or end the chat or session, or that they are
  done for now (in any language: "chiudiamo", "fine sessione", "basta per oggi"…), run the `litcompass-close`
  procedure before anything else: append the diary entry, rewrite WIP.md, show both to the user.

## Commands

```bash
pip install -r requirements.txt                      # once (or: pip install -e .  → `litcompass ...`)
python -m litcompass init <slug> --title "..."       # new project in projects/<slug>/ (becomes active)
python -m litcompass projects | use <slug>           # list / switch projects; or -p <slug> before any command
python -m litcompass seeds search "query" [--since 2010] [--sort cited]   # Crossref, free
python -m litcompass seeds add DOI [DOI...] --note "why"                  # verified, written to project.yaml
python -m litcompass check --fetch                   # config sanity + how the filter scores the seeds
python -m litcompass vocab --from seeds              # words that really occur (also --from core --contrast rejected)
python -m litcompass run --max-minutes 15            # expand the graph (network); resumes where it stopped
python -m litcompass status --samples 10             # progress, filter samples, next step
python -m litcompass rescore                         # re-apply the filter after editing project.yaml (offline)
python -m litcompass study-plan [--focus REGEX]      # -> projects/<slug>/reports/study_plan.md
python -m litcompass reading-list [--topic REGEX]    # by thread, or by topic (personalized PageRank)
python -m litcompass paper DOI | find REGEX          # look inside the graph
python -m litcompass mark DOI --as read|reading|skip # study progress
python -m litcompass journal                         # WIP.md open items + last DIARY.md entry
python -m litcompass run --refresh 50                # maintenance: catch new papers citing the core
```

Files of a project (`projects/<slug>/`): `project.yaml` (yours and the user's), `DIARY.md` and `WIP.md` (yours, see
above), `data/` (code only), `reports/overview.md` and `reports/study_plan.md`, `exports/core_papers.csv`,
`study/progress.csv`.

## Rules that are not negotiable

1. **Your memory is not a source.** Never write a DOI, author, year, title or number you have not read in a tool
   output (`seeds search`, `paper`, `find`, the reports) or that the user gave you. To add a paper you "know",
   find it with `seeds search` first. If you add general knowledge to an explanation, label it
   **general knowledge — to verify** and keep it separate.
2. **Cite what you state.** Statements about the literature carry the DOI of the paper they come from and the level
   of the source: `abstract` (read in `paper DOI` or `data/nodes.jsonl`), `metadata` (title/venue only), or `full text`
   (only if the user gave you the paper). Say so when the graph does not cover a question.
3. **Free sources only.** OpenCitations, Crossref, and OpenAlex *single lookups by DOI* (cost 0). Never call
   OpenAlex search or filtered lists (metered), never add paid APIs or LLM API calls to the code.
4. **No bulk downloads from publishers**, no scraping of PDFs. Full texts are obtained by the user, one at a time;
   open-access links come from the data. **Never commit PDFs** (`*.pdf` is in `.gitignore`).
5. **Do not edit `data/` by hand**: it is managed by `run` and `rescore`. Change behaviour through `project.yaml`.
6. **Ask before decisions that cost the user time or scope**: adding/removing seeds, raising `max_core_nodes`
   (the size of the graph), setting or raising `max_depth`, deleting a project.
7. Keep the console output in mind: large files (`nodes.jsonl`, `edges.csv`) are read with the commands above or
   with grep, never loaded whole into the conversation.

## Working on the code

- Python ≥ 3.10, dependencies in `requirements.txt`. Tests: `python -m pytest` (offline, a fake citation network).
- The architecture and its rationale are in `docs/ARCHITECTURE.md`; update it when you change a design decision.
- Keep the filter deterministic and the pipeline free: if a feature needs a model, it belongs in a skill, not in code.
