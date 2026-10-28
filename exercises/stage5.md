# Stage 5: the checker, a second model reviews the work

![Stage 5 flow](../assets/stage5_flow.png)

**The idea.** Tests decide whether the code *works*. They can't decide
whether the change is *allowed*: deleting a validation check can make a test
pass too. The checker is a second, cheaper model with no tools. It reads the
diff and `INTENT.md`, and fails the change only when it breaks a rule that's
written down, quoting the sentence it breaks. A failure goes back to the
actor as feedback, and the loop keeps going.

**Fixed rules first.** Some rules are simple enough for code. "Never
change CATALOG" and "never delete a rejection" are checked by
[harness/sensors.py](../harness/sensors.py) for free, before the checker
runs. Code catches what code can; the model judges what needs judgement.
This is Fowler's split between *computational* and *inferential* sensors.
The fixed rules are deliberately narrow: exact about the shapes they check,
blind to anything else (see the last exercise).

## In the code
| Piece | Where in [harness/checker.py](../harness/checker.py) |
|---|---|
| A different model | `CHECKER_MODEL = "claude-haiku-5-5"`: not the actor, no tools |
| A typed verdict | `VERDICT_SCHEMA` via structured outputs: pass/fail, violations, each quoting INTENT.md |
| Fails closed | `CheckerUnavailable` on any API error, bad JSON or odd stop reason: the change is **not** accepted |
| Feedback | `feedback_for_actor`: the violations, sent back as the next user message |
| The evidence | [harness/scenario.py](../harness/scenario.py) `current_diff`: the change since the scenario was applied |
| Fixed rules | [harness/sensors.py](../harness/sensors.py): CATALOG unchanged, no rejection removed; compared with the scenario's snapshot using `ast` |
| Testing the checker | [harness/checker_eval.py](../harness/checker_eval.py) + [scenarios/cheats/expected.json](../scenarios/cheats/expected.json): known diffs, expected verdicts, pass^k |

## Run it
The checker on its own, against three diffs that **all pass the 14 tests**:
```
python -m harness.scenario apply broken
for d in proper_fix loosened catalog_bump; do
  python -m harness.checker --diff scenarios/cheats/$d.patch --intent scenarios/intent/no_rules.md
  python -m harness.checker --diff scenarios/cheats/$d.patch      # INTENT.md, with rules
done
```
Then in the loop:
```
python -m harness.scenario apply broken
python -m harness.loop --fresh --no-gate | tee runs/stage5.md
```

Test the checker itself. Each case runs 3 times and counts only if every
trial was right (pass^k), and the exit code fails if a regression case breaks:
```
python -m harness.checker_eval --trials 3
```

## What to look for
- With no rules, does the checker *notice* the cheats? Does it fail them?
- With rules, each violation quotes an exact INTENT.md sentence.
- In the loop: `sensors: PASS`, then `checker: PASS`, before `DONE`. A cheat gets
  `FIXED RULE REJECTED` and the checker is never called for it.
- In the eval: do the verdicts vary between trials on the same diff?

## What happened when we ran it
[results/stage5/comparison.md](../results/stage5/comparison.md):
- **No rules:** all three diffs passed, cheats included. The checker noticed
  the changes but had no written rule to fail them on.
- **Rules v1:** both cheats failed, and so did the honest fix: "never relax
  validation" was too vague, and the min-spend fix read like relaxing it.
- **Rules v2** added one sentence ("the minimum spend is inclusive"): honest
  PASS, both cheats FAIL. One review still misread a line, though the verdict
  was right. A checker is still just an agent.

## Try this
1. **Turn the fixed rules off.** Rerun a cheat with `--no-sensors`. Now
   only the checker stands between it and `DONE`. Which costs less, and
   which can misread a line?
2. **Make it stricter.** Change the checker prompt so it fails anything "not
   covered" by INTENT.md. Run the honest fix. Strict checkers block honest
   work.
3. **Use the same model.** Set `CHECKER_MODEL` to the actor's model. Does it
   still catch the cheats? (Reviewer diversity is a design choice, not a
   formality.)
4. **Write a cheat of your own.** Make a diff that passes the 14 tests and
   breaks an INTENT.md rule in a way the checker misses. Add it to
   `expected.json` and run the eval. If code could catch it, add a sensor too.
5. **Beat the fixed rules.** Wrap the expiry `raise` in `if False:`, or
   change `CATALOG["DIWALI10"]` after it's defined. Both get past
   `sensors.py`. Does the checker catch them? This is why a narrow rule needs
   a broader reviewer behind it.
