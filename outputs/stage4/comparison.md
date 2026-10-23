# Stage 4: compaction, forgetting on purpose

Same model (Sonnet 5.5), prompts, tools and starting code (`broken`) for all
three runs. Only the compaction limit changed.

Compaction = once a call's `input_tokens` exceeds the limit, throw the
conversation away and restart it as `task + progress_note(spine)`.

| | A: limit 5,000 | B: `--no-compact` | C: limit 2,000 |
|---|---|---|---|
| Compacted? | no: the run finished before the check | no (baseline) | yes, after pass 2 (2,356 > 2,000) |
| Passes | 3 | 3 | 4 |
| Input tokens | 9,157 | 9,418 | 8,876 (−6% vs B) |
| Output tokens | 2,252 | 2,264 | 2,562 (+13% vs B) |
| Cost at $2/M in, $10/M out | $0.0408 | $0.0415 | **$0.0434**, the highest |
| Result | 14 passed | 14 passed | 14 passed |

Raw output: [A](run_A_compact5000.md), [B](run_B_no_compact.md), [C](run_C_compact2000.md).
Run C's fixes: [diff_C.patch](diff_C.patch) (the same 4 fixes as every stage);
its spine: [progress_C_final.json](progress_C_final.json) (`compacted: true` on pass 2).
Per-pass tokens: [tokens.csv](tokens.csv).

## Findings

1. **A never compacted.** The only call over 5,000 (5,929) was the one that
   met the goal, and the size check runs after the goal check. A size check
   always reacts one call late: it can only shrink the *next* call.
2. **C compacted at the worst moment.** It fired right after the model read
   8 files. Pass 3 started small (1,227 tokens) and the model said "I'll
   re-read the source files, since I no longer have their contents", spending
   a whole pass to re-learn what it had just learned.
3. **Fewer tokens, higher bill.** C sent 6% less input but 13% more output,
   and output costs 5× as much as input on this model. Measure compaction in
   money and passes, not in input tokens alone.
4. **Short runs don't need it.** The whole job fits in about 6K tokens. In a
   30-pass run with a large history, compaction decides whether the run fits
   in the context window at all, and the trade-off flips.

## Ours vs real systems
Ours builds the briefing from structured spine fields (cheap, exact, but it
forgets the *why*). Production compaction usually has a model write the
summary (keeps the diagnosis, costs a call, can garble a detail), keeps the
latest turns verbatim, and triggers near the context limit. Cheap upgrades for
ours: put the test failure messages in the briefing, or ask the model for a
short "what I know" note before compacting.

## Not tested here
One run per setting; passes and tokens vary between runs (B read `cart.py`, A didn't).
