---
name: litcompass-close
description: Close a litcompass work session - append what was done to the project's DIARY.md and rewrite WIP.md so the next chat can resume. Use whenever the user says they want to close, end or stop the chat or session, or that they are done for today (e.g. "chiudiamo", "chiudo la chat", "fine sessione", "basta per oggi", "let's wrap up"), or invokes /litcompass-close.
---

# litcompass-close — diary and WIP at the end of a session

Every project folder (`projects/<slug>/` or `$LITCOMPASS_HOME/<slug>/`) has two journal files:
- `DIARY.md`: what was done, one entry per session, **append-only** (never rewrite or delete past entries);
- `WIP.md`: what is open, **rewritten** at every close so that the next session knows where to start.

Write both in the user's language. Rules in `AGENTS.md` apply: only facts from this session and from tool output,
no invented numbers.

## Steps

1. Identify the project(s) worked on in this session (usually the active one: `python -m litcompass projects`).
   Repeat the steps below for each project touched.
2. Collect the facts:
   - `python -m litcompass journal` (creates the files if missing, shows the current WIP and the last entry);
   - `python -m litcompass status` (papers, waves, stop reason, reading progress);
   - this conversation: commands run, results, decisions and the reasons the user gave, problems met.
3. **Append** a diary entry at the end of `DIARY.md`:
   ```markdown
   ## YYYY-MM-DD — <short title of the session>
   - Done: <actions and results, with numbers: seeds added, runs and minutes, papers screened/admitted>
   - Decisions: <what was decided and why, in the user's terms>
   - Graph: <papers in the graph, last wave and its admission rate, stop reason>
   - Reading: <papers marked read/reading, with DOI, if any>
   - Problems: <what did not work and how it was handled; omit the line if none>
   ```
   Keep it short (5–12 lines). Use today's date. Do not repeat what earlier entries already say.
4. **Rewrite** `WIP.md`, keeping its sections:
   - `## Next session starts with`: the single first step for the next chat, concrete enough to paste
     (e.g. `/litcompass-build` → continue the runs until saturated; or a precise question to the user);
   - `## To do`: open items as `- [ ]`, most important first; remove items completed in this session (they are in the
     diary now); add the new ones that emerged;
   - `## Open questions for the user`: decisions only the user can take (seeds, size cap, scope);
   - `## Later`: ideas and nice-to-haves.
   Keep it under ~40 lines.
5. Reply to the user with: the diary entry (as written), the "Next session starts with" line, and a confirmation
   that the session can be closed. To resume in a new chat: `/litcompass-build` or `/litcompass-study` (or just
   "continue"): agents read `WIP.md` at the start of every session.

If the session changed nothing on any project (only questions), say so and update nothing unless the user asks.
