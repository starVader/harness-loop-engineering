# Outputs: the lab notebook

One folder per stage, holding the evidence from the run that taught something.
Exercises say *what to do*; this folder shows *what actually happened*.

## The rule
Every run writes raw output to `runs/` (gitignored, throwaway). When a run is
worth keeping, copy it into `outputs/stageN/` and commit it.

## What a stage folder holds
| File | What it is | Example |
|---|---|---|
| `tests_before.txt` | pytest output before the loop runs | `4 failed, 10 passed` |
| `transcript.md` | each pass: the tool the model called and what came back | `pass 2: write_file(checkout/discounts.py)` |
| `diff.patch` | what the loop changed: `git diff broken -- checkout/` | `-    if subtotal <= ...` |
| `tests_after.txt` | pytest output after the loop | `14 passed` |
| `tokens.csv` | input/output tokens per pass | `pass,input,output` |
| `notes.md` | your takeaway, in your own words | one paragraph |

Not every stage needs every file; each exercise lists what to save.

## Stages
| Stage | Folder | Status |
|---|---|---|
| 0 Scaffold | [stage0/](stage0/) | done: green, broken and guardrail evidence |
| 1 Bare loop | [stage1/](stage1/) | done: goal met on pass 3, 4 fixes |
| 2 Bad goal vs oracle | [stage2/](stage2/) | done: both fixed the bugs; self-assessed cost 62% more input |
| 3 Spine | [stage3/](stage3/) | done: crash + resume finished on pass 4; rerun is a no-op |
| 4 Context | stage4/ | next |
| 5 Checker | stage5/ | |
| 6 Intent debt | stage6/ | |
| 7 Human gate | stage7/ (your fix explanations go here) | |
| 8 Triggers | stage8/ | |
