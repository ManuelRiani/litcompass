# Architecture

litcompass is a generalisation of a private tool built to map the literature on piezoelectric MEMS resonators
(about 3,800 papers, tuned over several weeks). This document records how it works and why.

## 1. Principles

| Principle | Consequence |
|---|---|
| Zero marginal cost | Only free, keyless sources. OpenAlex is used only for single lookups by DOI, which cost 0 in its usage-based pricing (Feb 2026); searches and filtered lists are metered and never called. If OpenAlex ever reports a cost for a lookup, the client stops using it for the run and falls back to Crossref. |
| Deterministic pipeline | No model in the code: the filter, ranking and clustering are reproducible and run anywhere (laptop, CI). Work that needs judgement (choosing seeds and terms, writing advice) is done by the user's agent, through skills. |
| The model is not a source | Agents may only state papers and facts read from tool output. Seeds are verified by a lookup before being written. |
| Local first, private by default | Projects live in `projects/` (git-ignored) or in `$LITCOMPASS_HOME`. |
| Text files | `nodes.jsonl`, `edges.csv`, `runs.csv`: diffable, greppable, no database. |
| Respect publishers | No PDF download or scraping. Open-access links come from OpenAlex metadata. |

## 2. Layout

```
litcompass/            Python package (CLI: python -m litcompass)
  config.py            projects, active project, defaults
  sources.py           OpenCitations, OpenAlex lookup, Crossref (metadata, references, search)
  store.py             nodes/edges/runs on disk
  relevance.py         the filter
  run.py               expansion loop and refresh (maintenance)
  rescore.py           offline re-filtering
  report.py            PageRank, Louvain threads, overview.md, exports
  study_plan.py        staged study path
  reading_list.py      by thread / by topic (personalized PageRank)
  seeds.py vocab.py check.py inspect_cmd.py progress.py status.py cli.py
templates/project.yaml template of a new project
examples/              tuned example project
.claude/skills/        agent workflows (Claude Code and GitHub Copilot)
.github/prompts/       the same workflows as VS Code prompt files
AGENTS.md CLAUDE.md .github/copilot-instructions.md   agent instructions
```

## 3. Expansion (`run.py`)

1. Seeds enter at wave (depth) 0 (metadata fetched once).
2. Breadth-first by waves, until time is up, the cap is hit or nothing is left:
   1. expand every admitted paper of the nearest wave (seeds first, then most linked, then most cited): references
      always; citing papers only for seeds and for papers that are relevant (`score ≥ admit_score_linked`) and not
      hubs (`cited_by ≤ forward_max_cited_by`);
   2. screen every candidate discovered by that wave, best connected first (screening after the whole wave is
      expanded means each candidate is judged with all its links known);
   3. move to the next wave.
3. Stop conditions: `max_core_nodes` (the size of the graph) or **saturation** (no candidate passes the filter, the
   frontier closes by itself). Because waves are processed in order, a graph
   cut by the cap contains the nearest papers, and in the last wave the best connected ones. Admissible papers found
   after the cap stay `candidate`: raising the cap resumes from them.
4. Why no depth limit (removed in 0.2): citation distance is not topical distance. A narrow topic can be exhausted at
   distance 2 while relevant work sits at 3; a broad topic explodes at 2 (×8 per wave in the original MEMS graph).
   Relevance is the filter's job; size is the cap's. The depth is still tracked, as a drift indicator: `status`
   prints admitted/screened per wave and warns when the rate jumps up (drift) or falls under 2% (saturation).
5. Checkpoint every `checkpoint_minutes`; every run is logged in `runs.csv` and resumes from the saved state.
6. **Refresh** (`--refresh K`): re-downloads the citing papers of the K most central papers whose last refresh is
   older than `--min-age-days`; new papers go through the normal filter and expansion. This is the maintenance mode
   once the graph is complete.

Node states: `core`, `candidate`, `rejected` (metadata kept for `rescore`), `unresolved` (no metadata).

## 4. Relevance filter (`relevance.py`)

Score = Σ weights of matched regex terms; a match in the title counts double; weight-1 terms contribute at most
`weak_cap`; negative weights subtract. A paper is admitted if any of:

- it has a strong term (weight ≥ 2) and score ≥ `admit_score`;
- it is linked to ≥ 2 graph papers, has a strong term and score ≥ `admit_score_linked`;
- it is linked to ≥ `admit_links_any` graph papers and score ≥ 0.

Non-research types (errata, paratext, peer reviews, datasets…) and retracted papers are never admitted.
`rescore` recomputes everything offline after a change, iterating link-based admissions to convergence and
recomputing depths by BFS from the seeds. Why lexical and not embeddings/LLM: zero cost, reproducible, explainable
to the user ("which term let this in?"), and tunable in minutes with `status --samples` and `vocab --contrast`.

## 5. Map (`report.py`)

- **PageRank** (α = 0.85) on the directed graph of admitted papers: centrality within the user's perimeter, not
  global citation counts.
- **Threads**: Louvain (`report.resolution`, seed 42) on a similarity graph = direct citations (weight 1) +
  bibliographic coupling and co-citation (weight 1/(n−1) per shared paper, groups larger than 60 ignored).
  Clusters smaller than `min_cluster_size` go to group 0. Labels: c-TF-IDF on title uni/bigrams; words present in
  > 30% of all titles and `generic_terms` are excluded. Numbering can change between runs.
- `kind`: `review` (OpenAlex type or title pattern), `book` (book/chapter types), `paper`.

Determinism: nodes, edges and title terms are processed in sorted order, so the same graph always gives the same
clusters, numbers and labels (Python randomizes set order per process). This is what lets `threads.yaml` names stick:
each name is stored with the automatic terms of its thread and applied only while they match.

## 5b. 3D animation (`render.py`)

Spring layout in 3D (networkx, fixed seed) on the citation graph, with links inside a thread weighted ×3 so threads
form clouds. Each frame rotates the cloud around the vertical axis with a fixed tilt and a perspective projection
drawn with matplotlib 2D collections (depth sorted, nearer = brighter and bigger): about 1 s per frame for ~4000
papers. Default 96 frames at 10 fps: one turn in ~10 s, ~2 minutes of rendering, a GIF of ~10–12 MB.
Seeds are drawn as white dots. Lines: not every citation (a dense graph turns into fog) but, for each paper, its 2 closest links (same thread first, then most shared neighbours), `--links K` to change. The GIF uses a fixed palette (each hue blended with the surface at 18 opacities, plus grays) so the thread colors stay exact. Colors: the validated 8-hue categorical palette (dark-mode steps),
assigned to the 8 largest threads in fixed order; smaller threads fold into "other threads" (more hues would not be
distinguishable). Runs automatically when a run ends saturated or at the cap (`--no-render` to skip).

## 6. Study plan (`study_plan.py`)

Score = global PageRank, or PageRank personalized on the papers matching `--focus` / `study.focus`.

1. **Orientation**: top reviews/books, with at least a couple from the last 8 years.
2. **Foundations**: top research papers, shown oldest first.
3. **Threads**: top threads by summed score, their key papers oldest first.
4. **Frontier**: papers from the last `recent_years`, by citations inside the graph.

Seeds are excluded by default (the user chose them). Progress from `study/progress.csv` is shown as checkboxes.
The agent skill `litcompass-study` adds the part code cannot do: why each paper matters for *this* project and what
to look for in it, based on abstracts, adapted to the user's stated background.

## 7. Agent integration

- `AGENTS.md` is the single source of instructions (read natively by Copilot and other agents); `CLAUDE.md` imports
  it with `@AGENTS.md`; `.github/copilot-instructions.md` points to it.
- Skills follow the open Agent Skills format (`SKILL.md` with `name`/`description` frontmatter). Claude Code reads
  `.claude/skills/`; GitHub Copilot (VS Code, CLI, coding agent) reads `.github/skills/` and `.claude/skills/`,
  so one copy serves both. `.github/prompts/*.prompt.md` expose the same workflows as `/` commands in VS Code
  and simply link to the SKILL.md files.

## 7b. Session journal

Agents have no memory between chats, and the user may switch between Claude Code and Copilot. Each project therefore
keeps `DIARY.md` (append-only log, one entry per session) and `WIP.md` (open items and the first step of the next
session, rewritten at every close). `litcompass journal` prints both and creates them if missing (projects created
before this feature); `status` lists the open WIP items. The close procedure is the `litcompass-close` skill,
triggered when the user says they want to close the chat.

## 8. Running in the cloud (optional)

`.github/workflows/expand.yml` runs `python -m litcompass run` and commits the results. It needs the project data to
be committed: use it in a **private** fork/copy, remove `projects/*` from `.gitignore` for that project (or set
`LITCOMPASS_HOME` to a tracked folder), then enable the schedule in the workflow file.

## 9. Known limits and ideas

- Coverage gaps: no-DOI documents, missing deposited references, OpenCitations update lag (months).
- arXiv-only preprints are poorly covered; an arXiv/DataCite source could be added (free) in the future.
- Thread numbering is not stable across runs; a persistent mapping by overlap would help long-lived projects.
