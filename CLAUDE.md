@AGENTS.md

## Claude Code notes

- Skills are in `.claude/skills/` and can be invoked as `/litcompass-setup`, `/litcompass-build`, `/litcompass-study`.
- Long runs (`run --max-minutes 30`) can exceed the default command timeout: run them in the background or in
  shorter slices (`--max-minutes 8`); every run resumes where the previous one stopped.
