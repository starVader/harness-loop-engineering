# Stage 7: the human gate

**You learn:** the tests say the code *works* and the checker says the
change is *allowed*, but neither says anyone *understands* it. When a loop
merges code nobody can explain, the codebase builds up comprehension debt:
it passes today, and nobody can say why when it breaks. The gate is the
cheapest check of understanding there is: before a change is accepted, a
human explains each part of it in one sentence.

**Order matters.** The gate is the slowest, most expensive check, so it goes
last: tests (milliseconds, free), then checker (seconds, cents), then human
(minutes, attention). Never spend a human on a change the tests or the checker
would have rejected anyway.

## The gate (given): `gate.py`
| Function | What it does |
|---|---|
| `hunks(diff) -> List[GateItem]` | splits a diff into change blocks, even when git merged two of them into one hunk. Each block's id is the file plus a hash of its +/- lines |
| `unexplained(items)` | the blocks with no explanation yet in `outputs/stage7/fixes.md` |
| `ask_human(items) -> GateResult` | shows each block and asks for one sentence (6+ words), or `reject: <why>`; raises `GateUnavailable` without a terminal |
| `record(result)` | appends the session to `outputs/stage7/fixes.md` |
| `feedback_for_actor(result)` | the rejection message for the actor, like the checker's |

Because ids are hashes, an explanation sticks to the code it explains. Change
that block later and the old sentence no longer matches: `gate.py --check`
fails until someone explains it again. Stage 9's git hook relies on this.

Try it standalone before wiring it in:
```
venv/bin/python gate.py --diff stage5/diff_proper.patch --fixes runs/stage7-try.md
```

## How it's wired into `loop.py`
1. **Where:** both places the loop can accept a change (after a pass, and
   when the model stops) call `review_change`: checker first, then the gate.
   A change is accepted only when tests, checker *and* gate all pass. Only
   `unexplained(...)` blocks are shown, so a rework doesn't ask you again
   about blocks you've already explained.
2. **A rejection** goes back to the actor exactly as a checker rejection
   does (`GATE REJECTED` in the transcript), after any compaction, so
   forgetting can't drop it.
3. **No human** (`GateUnavailable`) stops the run without accepting it
   (`REVIEW UNAVAILABLE`). The gate fails closed, like the checker.
4. **The spine:** every `PassRecord` now has `gate` (`"pass"`, `"fail"`, or
   `null` when the gate is off or wasn't reached), alongside `checker`.
5. **`--no-gate`** skips the gate for unattended runs. Stage 8 uses it.
   Stage 9 will tempt you to use it more.

The gate is on by default now, so stage 1-6 commands will stop and ask you
too. Add `--no-gate` to repeat an old stage as it was.

`input()` flushes stdout first, so `| tee` still shows each block before
the prompt.

## Steps
1. **Run A: explain every fix.**
   ```
   git restore --source=broken -- checkout/ && venv/bin/python loop.py --fresh | tee runs/stage7-explain.md
   ```
   Write one sentence per block, in business words: *why* the change is
   right, not *what* the line now says ("rounds half-up" restates the code;
   "a half paisa is charged to the customer, never dropped" explains it).
2. **Run B: reject one.** Same command, `runs/stage7-reject.md`, but first
   rename `outputs/stage7/fixes.md` to `fixes_A.md`, so nothing counts as explained.
   Reject one block with a reason the actor can act on (for example, ask it
   to justify a change in terms of INTENT.md, or to take out a comment that
   restates the code). Watch the next pass: does the actor rework only that
   block, and does the gate ask you only about the new block?
3. **Try to explain a cheat.** Stage 5's loosened diff passes the tests:
   ```
   venv/bin/python gate.py --diff stage5/diff_loosened.patch --fixes runs/stage7-cheat.md
   ```
   Explain the `validate_code` block in one honest sentence. Notice what
   that sentence has to admit.
4. **Stale explanations.** After run A is accepted, change one line inside a
   block you explained (any harmless edit), then
   `venv/bin/python gate.py --check`. It should fail on exactly that block.
   Restore the line and it passes again.

## Save to `outputs/stage7/`
`fixes_A.md` and `fixes.md` (already there, written by the gate), both run transcripts,
your cheat sentence from step 3, and your `notes.md`.

## Questions for your notes
1. Which block took you longest to explain? Was the actor's own summary
   enough, or did you have to read the code and INTENT.md?
2. In step 3, could you write an honest sentence that a reviewer would
   accept? What did the gate catch that the stage 5 checker, with no rules,
   missed?
3. In run B, did the rejection steer the actor as precisely as a checker
   violation? What made your reason actionable, or not?
4. `--no-gate` exists for unattended runs. Which runs should never get it?
