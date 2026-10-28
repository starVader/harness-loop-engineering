# Results: what happened when we ran it

Real runs against the Claude API, one folder per stage, with transcripts,
diffs, token counts and a write-up. The exercises say what to run; this
folder shows what happened when we did.

These runs were recorded while the harness was being built, so file names
in the transcripts are from that time: `loop.py` was at the repo root,
`stage0/inject_bugs.patch` is now `scenarios/broken.patch`, the stage 5
diffs are now `scenarios/cheats/`, and "the broken baseline" is
`python -m harness.scenario apply broken`. The behaviour is the same.

| Stage | Folder | Headline |
|---|---|---|
| 0 Playground | [stage0/](stage0/) | 14 green → 4 failed, 10 passed; every guardrail escape refused |
| 1 Bare loop | [stage1/](stage1/) | goal met on pass 3 with all 4 fixes; an unfiltered `list_files` cost 144K tokens in one call |
| 2 Goal | [stage2/](stage2/) | both goals fixed the bugs; the self-assessed one used 62% more input and couldn't know it was right |
| 3 Spine | [stage3/](stage3/) | crash after pass 2, resume finished on pass 4; 43% less input than no crash; a rerun is a no-op |
| 4 Context | [stage4/](stage4/) | compacting at 2,000 cut input 6% and still cost the most: the model re-read what it forgot |
| 5 Checker | [stage5/](stage5/) | no rules: both cheats pass; vague rules: the honest fix fails; precise rules: only the cheats fail |
| 6 Intent | [stage6/](stage6/) | honest fix with and without rules; only the run with rules was accepted *by design* |
| 7 Human gate | stage7/ | not recorded yet: checked offline in `selftest/` |
| 8 Outer loop | stage8/ | not recorded yet: checked offline in `selftest/` |

## What a stage folder holds
| File | What it is |
|---|---|
| `comparison.md` | the write-up: setup, a table of runs, findings |
| `run_*.md`, `transcript.md` | each pass: tools called, verdicts, tokens |
| `*.patch` | what the loop changed |
| `tokens.csv` | input and output tokens per pass |
| `progress_*.json` | the spine at interesting moments |

## Adding your own
Raw output goes to `runs/` (gitignored). When a run teaches something, copy
it into `results/stageN/` with a short `comparison.md`: what you ran, what
happened, and what it shows.
