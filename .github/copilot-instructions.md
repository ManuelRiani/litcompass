# GitHub Copilot instructions

Read and follow [AGENTS.md](../AGENTS.md): it describes this repository (litcompass), its commands and the rules
that are not negotiable (no DOIs or facts from memory, cite DOIs, free sources only, no PDFs in git, do not edit
`projects/*/data/` by hand).

Workflows are agent skills in `.claude/skills/` (`litcompass-setup`, `litcompass-build`, `litcompass-study`,
`litcompass-close`) and
prompt files in `.github/prompts/` with the same names: type `/litcompass-setup` in Copilot Chat (agent mode).

At the start of a session read the project's `WIP.md` (`python -m litcompass journal`); when the user says they want
to close the chat, run `litcompass-close` (diary entry + new WIP.md) before anything else.

Reply in the user's language; keep code and files in English. Long graph runs: use `--max-minutes 8` slices, every
run resumes where the previous one stopped.
