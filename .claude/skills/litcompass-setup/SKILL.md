---
name: litcompass-setup
description: Start a new litcompass project from the user's research or engineering project - interview, project.yaml brief, verified seed papers, relevance vocabulary from real data, pilot run and first tuning. Use when the user wants to map the literature of a new topic, says "new project", "start", "set up", or invokes /litcompass-setup.
---

# litcompass-setup — from a project brief to a first citation graph

Goal: at the end the user has `projects/<slug>/project.yaml` with a clear brief, 3–15 verified seeds and a
vocabulary that admits papers like the seeds, plus a pilot graph they have reviewed. Reply in the user's language.
Follow the rules in `AGENTS.md` (nothing from memory, every DOI from a tool output or from the user).

Before starting: `python -m litcompass projects`. If `pip install -r requirements.txt` was never run, run it.

## 1. Understand the project (short interview)

Ask at most 5 questions, in one message, skipping what the user already said:
1. What are you working on, concretely (object, method, application)? What decision or output is ahead?
2. What do you want to be able to do after studying (design, thesis chapter, review, enter a new field)?
3. What do you already master, what is new to you?
4. What is explicitly **out** of scope (neighbouring applications, materials, methods)?
5. Papers, authors, groups, books or reviews you already know are central? (titles or DOIs are fine)

## 2. Create the project

```bash
python -m litcompass init <slug> --title "<short title>" --description "<2-5 line brief>"
```
Then edit `projects/<slug>/project.yaml`: fill `project.description` (concrete: object, methods, constraints),
`goals` (list) and `background` from the answers. Show the user the brief in 3 lines and ask for corrections.

## 3. Seeds (verified, never from memory)

1. For each paper the user named: `python -m litcompass seeds search "<title or topic words>" --rows 5` to get its DOI.
2. Derive 3–6 search queries from the brief (the object + the key phenomenon/method; one query for reviews:
   "review <topic>"). Run `python -m litcompass seeds search "<query>" --rows 15` (add `--sort cited` to see
   classics, `--since <year>` for recent work).
3. Build a shortlist of 5–12 candidates **only from the search outputs**: a recent review, 1–2 classics,
   the 2–5 papers closest to the project. Present it as a table (DOI, year, first author, title, why) and let the
   user pick. Hubs cited thousands of times are fine as seeds, but say that they pull in many citing papers (only
   relevant ones pass the filter).
4. `python -m litcompass seeds add <DOI> [<DOI>...]` (verifies each DOI, writes it with a note).

## 4. Vocabulary of the relevance filter (from data)

1. `python -m litcompass check --fetch` downloads the seeds' metadata and shows how they score (all ✗ at first).
2. `python -m litcompass vocab --from seeds --n 60` lists the words and phrases that really occur in the seeds.
3. Propose terms in `relevance.terms` of project.yaml, as case-insensitive regexes:
   - **3**: specific to the project (object, phenomenon, distinctive method); allow variants
     (`'thin[- ]film'`, `'resonat(?:or|ors|ing)'`, acronyms with `\b`: `'\bbaws?\b'`);
   - **2**: important but shared with neighbours; **1**: generic context (capped by `weak_cap`);
   - **-2 / -3**: the out-of-scope fields from question 4, and fields that share words with the topic.
   Explain the choice in a short table; the user decides. Quote YAML regexes with single quotes.
4. `python -m litcompass check` again: every seed that is a real example of the topic should be ✓ (score ≥
   `admit_score` with a strong term). Seeds with no abstract score only on the title: that is acceptable.

## 5. Pilot run and first tuning

1. Pilot: `python -m litcompass run --max-minutes 8` (it also writes the report). Expect a few hundred screened
   papers. For Claude Code, if the command may exceed the timeout, run it in the background.
2. `python -m litcompass status --samples 10`: show the user (a) a sample of admitted papers, (b) the
   highest-scoring rejected ones. Ask: which admitted ones are off-topic, which rejected ones should be in?
3. Fix terms accordingly (`python -m litcompass vocab --from core --contrast rejected` and
   `--from rejected --contrast core` show discriminating words), then `python -m litcompass rescore`.
   Repeat until the samples look right (usually 1–3 rounds).
4. Agree the size: `limits.max_core_nodes` is the main stop (1000–3000 for a study project, more for a thesis-level
   map). The graph grows wave by wave until that size or until the filter admits nothing more (saturated).
   `max_depth` stays `null` unless the user wants a hard perimeter (e.g. 1 = only direct neighbours of the seeds).

## 6. Hand over

Tell the user how to continue building (`python -m litcompass run` repeatedly, or the optional GitHub Action in
`docs/ARCHITECTURE.md`) and that when `status` says *complete*, the `litcompass-study` skill produces the study plan.
If the pilot graph already has more than ~100 papers, offer a first `study-plan` right away.
