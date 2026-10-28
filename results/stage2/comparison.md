# Stage 2: self-assessed goal vs pytest goal

Same model (Sonnet 5.5), system prompt, tools, 8-pass cap and starting code
(`broken`). Only the goal sentence in the task changed.

| | Run A: `--goal self` | Run B: `--goal pytest` |
|---|---|---|
| Goal given | "Make the checkout service better." | "Every test in tests/ passes." |
| Who decided "done" | the model (`end_turn`) | loop.py (`run_tests().exit_code == 0`) |
| Passes | 5 | 4 |
| How it ended | ACCEPTED ON THE MODEL'S WORD | DONE: goal verified on pass 4 |
| Observer: tests after | 14 passed | 14 passed |
| Tokens in / out | 25,306 / 2,848 | 15,627 / 2,156 |
| Code changed | the 4 fixes + explanatory comments | the 4 fixes |
| Summary with assumptions | yes | no (run ended before the model spoke again) |

Raw output: [run_self.md](run_self.md), [run_pytest.md](run_pytest.md).
Diffs: [diff_self.patch](diff_self.patch), [diff_pytest.patch](diff_pytest.patch).
Per-pass tokens: [tokens.csv](tokens.csv).

## Findings

1. **The vague goal still fixed all 4 bugs, because the system prompt carried
   the real goal.** It says the code must "behave the way the tests describe"
   and to run the tests first. The model's goal is everything in its context,
   not the sentence labelled "goal".
2. **Run A was right, but the loop could not know it.** `ACCEPTED ON THE
   MODEL'S WORD` prints the same whether the tests pass or fail; only the
   outside observer showed it was true. A stub run with a model that stops
   while 4 tests fail gets the identical verdict.
3. **Self-assessment cost 62% more input tokens.** Run B wrote the fixes and
   ran the tests in one pass, and loop.py stopped it immediately. Run A spent
   one extra pass running the tests itself and another writing a summary, each
   re-sending the ~8K-token history.
4. **Trade-off:** run A's summary (with its assumptions) is useful, and run B
   threw it away. Best of both: code decides "done", then ask the model for the
   summary. That is the stage 7 gate in miniature.

## Not tested here
- A self-assessed run *without* the oracle in the system prompt (stage 2b).
  That is the run where drift should become visible.
- Variance: one run per goal. A second run could differ in passes and tokens.
