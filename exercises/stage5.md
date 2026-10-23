# Stage 5: the checker, a second model reviews the work

![Stage 5 flow](../assets/stage5_flow.png)

**You learn:** the tests decide whether the code *works*; a checker decides
whether the change is *allowed*. A checker can only enforce intent that is
written down, and only as precisely as it is written.

**You build:** `checker.py`, and the checker wired into `loop.py` after the
goal is verified (`--no-check` to skip it).

## The checker
| | |
|---|---|
| Model | `claude-haiku-5-5`: different and cheaper than the actor, no tools, low effort |
| Input | `git diff broken -- checkout/` + `INTENT.md` |
| Output | structured verdict: `pass`/`fail`, violations quoting the INTENT.md sentence broken |
| Rule | fail only on what INTENT.md states; name uncovered behaviour in the summary |
| Failure | API error, `max_tokens`, bad JSON or no text → `CheckerUnavailable` → change **not** accepted |

In the loop: goal verified → checker. Pass → DONE. Fail → the violations go
back to the actor as the next message (after any compaction, so they can't be
forgotten) and the loop continues.

## Steps
1. Write `checker.py` with a typed verdict and a standalone CLI
   (`--diff`, `--intent`).
2. Wire it into both "goal verified" paths in `loop.py`; record `checker` per pass in the spine.
3. Stub-test: pass, reject-then-pass, rejection + compaction, checker down, `--no-check`.
4. Build test diffs that pass all 14 tests: the honest fix and two cheats
   (see `stage5/README.md`).
5. Predict, then run the matrix: 3 diffs × {`INTENT.md`, `stage5/intent_with_rule.md`}:
   ```
   for d in proper loosened catalog_bump; do for i in INTENT.md stage5/intent_with_rule.md; do venv/bin/python checker.py --diff stage5/diff_$d.patch --intent $i; echo; done; done | tee runs/stage5-matrix.md
   ```
6. If an honest fix fails, fix the **rule text**, not the checker, and rerun
   the whole rules column.

## Save to `outputs/stage5/`
`matrix_v1.md`, `rules_v2.md`, `intent_rules_v1.md`, `intent_rules_v2.md`,
`comparison.md`, your `notes.md`.

## Questions for your notes
1. Why did both cheats pass against the original INTENT.md, even though the
   checker noticed them?
2. Why did the honest fix fail under rules v1, and what fixed it?
3. The catalog-bump review gave one wrong reason. What does that mean for
   trusting a checker on its own?

**Our result:** see [outputs/stage5/comparison.md](../outputs/stage5/comparison.md).
