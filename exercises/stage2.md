# Stage 2: who decides "done"?

![Stage 2 flow](../assets/stage2_flow.png)

**The idea.** "Make it better" is a goal only the model can judge, so the
loop has to take its word: it stops when the model stops talking. "Every
test passes" is a goal code can check, so the loop stops when it's true,
whatever the model thinks. Same loop, same model; the only difference is
who holds the stop button.

## In the code
| Piece | Where |
|---|---|
| The goal interface | [harness/goal.py](../harness/goal.py) `Goal.is_met() -> True / False / None` |
| `PytestGoal` | `run_tests().exit_code == 0`: verified |
| `SelfAssessedGoal` | always `None`: code can't check it |
| The verdicts | [harness/loop.py](../harness/loop.py): `DONE` vs `ACCEPTED ON THE MODEL'S WORD` vs `STOPPED EARLY` |
| The observer | the last lines of every run: tests after, the same for every goal |

## Run it
```
python -m harness.scenario apply broken
python -m harness.loop --fresh --goal self --no-check --no-gate --no-compact | tee runs/stage2-self.md
python -m harness.scenario apply broken
python -m harness.loop --fresh --goal pytest --no-check --no-gate --no-compact | tee runs/stage2-pytest.md
```

## What to look for
- How each run ends: `ACCEPTED ON THE MODEL'S WORD` or `DONE: goal verified`.
- The `observer:` line. It's the only thing that tells you whether the
  self-assessed run was actually right.
- Total tokens: who stopped first?

## What happened when we ran it
[results/stage2/comparison.md](../results/stage2/comparison.md): both runs
fixed all 4 bugs, because the system prompt carried the real goal ("behave
the way the tests describe"). But the self-assessed run used **62% more
input tokens**, and its verdict would have printed exactly the same if the
tests had still been failing.

## Try this
1. **Remove the hidden oracle.** Delete "behave the way the tests describe"
   and "run tests" from `SYSTEM_PROMPT` and rerun `--goal self`. Does "make it
   better" still mean "fix the 4 bugs"? Check the observer line.
2. **A goal with no oracle.** Add a `ReadableGoal` to `goal.py` whose
   description is "Make the code easier to read" and whose `is_met` returns
   `None`. What does the loop accept? What would you need to make it
   checkable?
3. **Keep the summary.** The pytest run stops before the model explains its
   changes. Add one extra call after `DONE` that asks for a summary only. (The
   stage 7 gate is a stricter version of this.)
