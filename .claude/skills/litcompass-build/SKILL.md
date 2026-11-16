---
name: litcompass-build
description: Grow and maintain an existing litcompass citation graph - run expansion slices, read status, tune the relevance filter with samples and rescore, raise caps, refresh for new papers. Use when the user asks "where are we with the graph", "continue building", "too many off-topic papers", "update the graph", or invokes /litcompass-build.
---

# litcompass-build — grow, tune and maintain the graph

Reply in the user's language. Rules in `AGENTS.md` apply (do not edit `data/`, free sources only).
Select the project first: `python -m litcompass projects` (`use <slug>` or `-p <slug>` before the command).

## Where are we

`python -m litcompass status` → summarise in 3–5 lines: size vs cap, phase, last runs, errors, next step.

| Phase printed by status | What to do |
|---|---|
| building | continue with runs (below) |
| stopped at max_core_nodes | ask the user: raise `limits.max_core_nodes`, or tighten the filter and `rescore` |
| complete at max_depth | the graph is done: hand over to `litcompass-study`; maintenance with `--refresh` |
| runs ending with `error:` | read the message; network errors are retried next run; a suspended OpenAlex falls back to Crossref |

## Continue building

`python -m litcompass run --max-minutes 8` and repeat; each run resumes where the previous stopped and rewrites
the report. ~1–2 requests per second: 8 minutes ≈ 600–900 papers screened. Long builds: suggest running
`python -m litcompass run --max-minutes 30` from the user's own terminal, or the optional GitHub Action
(`.github/workflows/expand.yml`, see `docs/ARCHITECTURE.md`).

## Tune the filter

1. `python -m litcompass status --samples 10` and show both lists: admitted (false positives?) and the best rejected
   (false negatives?). Notation `[score|strong|links]`.
2. Find discriminating words with data, not memory:
   - `python -m litcompass vocab --from core --contrast rejected` → candidate positive terms;
   - `python -m litcompass vocab --from rejected --contrast core` → candidate negative terms;
   - `python -m litcompass find "<regex>" --all` → how many graph/rejected papers a term would touch.
3. Propose a small diff of `relevance` in project.yaml (terms, weights, or thresholds `admit_score`,
   `admit_score_linked`, `admit_links_any`), explain the expected effect, apply after the user agrees.
4. `python -m litcompass rescore` (offline) prints `+gained / -lost`; check samples again. Newly admitted papers are
   expanded by the next run.

Guidelines: prefer adding a precise strong term over lowering thresholds; negative terms for whole neighbouring
fields; `weak_cap` limits generic words. A seed that stops scoring is a sign the filter drifted.

## Scope changes (ask first)

- **Seeds**: `seeds search` → `seeds add DOI` / `seeds remove DOI`, then `rescore` and a run.
- **Depth**: `limits.max_depth` +1 multiplies the graph size; propose it only if the study plan feels thin.
- **Threads too coarse/fine**: `report.resolution` (higher = more, smaller threads), then `python -m litcompass report`.
  Labels polluted by the field's name: add it to `report.generic_terms`.

## Maintenance

Once complete, run monthly: `python -m litcompass run --refresh 50 --max-minutes 10` re-downloads the citing
papers of the 50 most central papers not refreshed in the last 30 days; new relevant work enters and is expanded.
