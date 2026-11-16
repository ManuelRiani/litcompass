# litcompass

**Map the literature around your project, then get told what to study, in what order.**

You describe your project. litcompass starts from a handful of seed papers, follows citations in both directions,
keeps only what is relevant to you, and turns the resulting citation graph into:

- a **map** of the field: foundational papers, research threads, recent work (`reports/overview.md`);
- a **study plan**: orientation → foundations → threads → frontier, with progress tracking (`reports/study_plan.md`);
- **reading lists** by thread or by topic, ranked by (personalized) PageRank, with open-access links when known.

It is designed to be driven by an AI coding agent: open the folder in **Claude Code** or **VS Code with GitHub
Copilot**, say what you are working on, and the agent runs the setup interview, finds and verifies seeds, builds the
relevance filter from real vocabulary, tunes it with you, and turns the plan into study advice.

**Zero cost, no keys.** [OpenCitations](https://opencitations.net) for the citation graph,
[OpenAlex](https://openalex.org) only for free single-paper lookups by DOI (metadata, abstract, open-access link),
[Crossref](https://www.crossref.org) for fallback metadata and seed search. No LLM API calls in the code, no paid
endpoints, no PDF downloads.

## Quick start with an agent

```bash
git clone https://github.com/ManuelRiani/litcompass
cd litcompass
pip install -r requirements.txt
```

Then, in the folder:

| Tool | How to start |
|---|---|
| Claude Code | `claude`, then `/litcompass-setup` (or just: "I want to map the literature for my project on …") |
| GitHub Copilot (VS Code, agent mode) | Copilot Chat → Agent → `/litcompass-setup` |
| Copilot CLI / other agents | ask them to follow `AGENTS.md` and `.claude/skills/litcompass-setup/SKILL.md` |

Three workflows ship with the repo, as [agent skills](https://agentskills.io) in `.claude/skills/` (read by both
Claude Code and Copilot) and as VS Code prompt files in `.github/prompts/`:

| Skill | What it does |
|---|---|
| `/litcompass-setup` | Interview → project brief → verified seeds → relevance vocabulary → pilot run → first tuning |
| `/litcompass-build` | Continue building, status, filter tuning with samples, caps, monthly refresh |
| `/litcompass-study` | Study plan tailored to your goals and background, reading lists, Q&A with DOIs, progress |

The agent instructions (`AGENTS.md`, imported by `CLAUDE.md` and referenced by `.github/copilot-instructions.md`)
forbid the agent from inventing papers: every DOI comes from a search result or from you, and every statement
about a paper cites its DOI and whether it comes from the abstract or only the metadata.

## Quick start without an agent

```bash
python -m litcompass init my-topic --title "My topic"
python -m litcompass seeds search "your topic keywords" --sort cited
python -m litcompass seeds add 10.xxxx/yyyy 10.xxxx/zzzz      # verified before being written
# edit projects/my-topic/project.yaml: description and relevance.terms (see the comments in the file)
python -m litcompass vocab --from seeds                        # words that really occur in your seeds
python -m litcompass check --fetch                             # do your seeds pass your own filter?
python -m litcompass run --max-minutes 15                      # repeat until `status` says complete
python -m litcompass status --samples 10                       # review admitted / rejected samples
python -m litcompass study-plan                                # -> projects/my-topic/reports/study_plan.md
python -m litcompass mark 10.xxxx/yyyy --as read               # track progress
```

`pip install -e .` also gives you a `litcompass` command. All commands: `python -m litcompass --help`.

## How it works

1. **Seeds** (`project.yaml → seeds`) enter the graph at depth 0.
2. Each admitted paper is **expanded**: its references and, if it is relevant and not a mega-hub, its citing papers.
3. Every discovered paper is **screened** by a deterministic filter: weighted regex terms on title and abstract
   (title counts double, negative weights for off-topic fields), combined with how many graph papers it is linked
   to. A rejected paper can come back later if it becomes well connected.
4. Expansion proceeds in waves up to `max_depth`, most central papers first. Runs are resumable.
5. **Report**: PageRank for importance, Louvain clustering on direct citation + bibliographic coupling +
   co-citation for research threads, labels from distinctive title terms.
6. **Study plan**: reviews/books for orientation, the most central papers in chronological order, the key papers of
   each thread, and the recent papers the graph already cites most. `--focus REGEX` bends everything towards a
   sub-topic with personalized PageRank.

Details and design rationale: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Your data

Each project lives in `projects/<slug>/` (git-ignored by default, so your topics stay private even in a public
clone). Set `LITCOMPASS_HOME` to keep projects elsewhere, e.g. in a private repo or a synced folder.

| File | Content |
|---|---|
| `project.yaml` | brief, seeds, relevance filter, limits — the only file you (or your agent) edit |
| `reports/overview.md` | the map |
| `reports/study_plan.md` | the study plan, with checkboxes |
| `exports/core_papers.csv` · `exports/core.graphml` | table and graph for Excel, Gephi, Cytoscape, networkx |
| `data/` | all papers seen (admitted, rejected, pending) and all citations — managed by the code |
| `study/progress.csv` | what you read, with notes |

Optional environment variables: `CONTACT_EMAIL` (added to the User-Agent and Crossref requests: polite and
faster), `OPENCITATIONS_TOKEN` (free token, higher limits), `OPENALEX_API_KEY` (free key; lookups are free anyway).

An example of a real, tuned project is in [`examples/mems-resonators/`](examples/mems-resonators/project.yaml).

## Limits

- Coverage is that of OpenCitations and Crossref: papers without a DOI (many theses, some books, arXiv-only
  preprints) and references not deposited by publishers are missed. OpenCitations lags a few months.
- Abstracts are missing for part of the literature (publishers that do not deposit them): those papers are judged
  on title and links only.
- The filter is lexical: it needs a few tuning rounds, which is what the agent workflow is for.

## License

MIT. Data retrieved from OpenCitations, OpenAlex (CC0) and Crossref follows their terms.
