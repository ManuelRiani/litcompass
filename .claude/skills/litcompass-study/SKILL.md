---
name: litcompass-study
description: Turn a litcompass citation graph into study advice tailored to the user's project - ordered study plan, reading lists by thread or topic, what to look for in each paper, progress tracking, and grounded answers to questions about the literature with DOIs. Use when the user asks what to read or study, for a study plan or path, "what next", about a sub-topic, or invokes /litcompass-study.
---

# litcompass-study — from the graph to a study path

Reply in the user's language. Rules in `AGENTS.md` apply: everything you say about a paper comes from tool output
(`paper`, `find`, reports) and carries its DOI; general knowledge is labelled **general knowledge — to verify**.

## 1. Context

1. `python -m litcompass status`. If the graph has fewer than ~80 papers or is still building, say the plan will be
   provisional and offer to continue building (`litcompass-build`).
2. Read the brief: the `project:` block of `projects/<slug>/project.yaml` (description, goals, background).
3. `python -m litcompass progress` to know what the user has already read.

## 2. Generate the plan

```bash
python -m litcompass study-plan                    # whole field
python -m litcompass study-plan --focus "<regex>"  # bent towards the project's core sub-topic
```
Choose `--focus` from the brief when the project is narrower than the graph (e.g. the goal is about one
phenomenon). Use a regex with variants (`"anchor loss|phononic|tether"`). The file is written to
`projects/<slug>/reports/study_plan.md`.

## 3. Turn it into advice (this is your added value)

For the first two stages (Orientation, Foundations) and the threads that matter for the goals:
1. Read the candidates with `python -m litcompass paper <DOI>` (abstract, thread, citations inside the graph).
2. For each paper you recommend, write 1–2 lines: **why now** (what it gives for the user's goal) and **what to look
   for** (the result, model or method stated in the abstract, marked `[abstract]`). If there is no abstract, say so
   and rely only on title and position in the graph.
3. Adapt to `background`: skip or shorten material the user already masters; add orientation where the user is new.
4. Group the work into sessions (e.g. 3–4 papers per week, or what the user says) and point out open-access links
   (`OA` in the outputs). For paywalled papers, the DOI link is where the user gets the PDF, manually.
5. Write the advice into `projects/<slug>/reports/study_advice.md` if the user wants to keep it (it is not
   overwritten by the code), and summarise it in the reply.

Threads: say which threads you recommend, which to skim, which to skip for this project, with one reason each
(using the thread label, size and years from the plan).

## 4. Targeted questions

- "What should I read on X?" → `python -m litcompass reading-list --topic "<regex>" --n 15`
  (✓ = mentions X, ○ = central for X without the keywords: often the foundations).
- "What is new?" → the Frontier stage, or `reading-list --since <year>`.
- "Which papers say Y?" → `python -m litcompass find "<regex>"`, then `paper DOI` for the best hits; answer with
  DOIs and the level `abstract`/`metadata`. If nothing matches, say the graph does not cover it and suggest seeds.

## 5. Progress

When the user reports reading: `python -m litcompass mark <DOI> --as read --note "<one-line takeaway>"`
(`reading`, `skip` also exist). Then regenerate the plan (`--hide-done` to hide finished items) and propose the next
step. A paper the user found important but outside the graph → suggest it as a seed (`seeds search`, `seeds add`).
