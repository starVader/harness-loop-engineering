# Stage 4: compaction, forgetting on purpose

![Stage 4 flow](../assets/stage4_flow.png)

**You learn:** every call re-sends the whole conversation, so cost grows with
history. Compaction trades memory for size, and *when* you forget matters as
much as *whether* you do.

**You build:** `compact_history()` in `loop.py`, one `if` after the spine is
saved, and two flags: `--compact-at N` and `--no-compact`.

## The mechanism
Once the last call's `input_tokens` exceeds the limit, restart the
conversation as one message: the task plus the spine's briefing. It's the same
mechanism as stage 3's resume, done on purpose.

## Three traps
| Trap | Fix |
|---|---|
| A resumed run's `task` already carries a briefing | keep a clean `base_task`; compact from that |
| The briefing says "after an interruption" when nothing crashed | `progress_note(spine, reason=...)` tells the model the truth |
| Compacting between a `tool_use` and its `tool_result` gets a 400 | compact only after the results are appended and the spine is saved |

A fourth isn't fixable cheaply: the size check sees the call that already
happened, so it always reacts one call late.

## Steps
1. Add `compact_history(task, spine)`, the `base_task` split and the `reason`
   parameter; record `compacted: True` on the pass in the spine.
2. Stub-test it: compaction on, off, and loading an older `progress.json`
   that has no `compacted` field.
3. Predict, then run three times from the broken baseline:
   ```
   git restore --source=broken -- checkout/ && venv/bin/python loop.py --fresh | tee runs/stage4-compact.md
   git restore --source=broken -- checkout/ && venv/bin/python loop.py --fresh --no-compact | tee runs/stage4-baseline.md
   git restore --source=broken -- checkout/ && venv/bin/python loop.py --fresh --compact-at 2000 | tee runs/stage4-compact2000.md
   ```

## Save to `outputs/stage4/`
The three runs, `diff_C.patch`, `progress_C_final.json`, `tokens.csv`,
`comparison.md`, your `notes.md`.

## Questions for your notes
1. Why did the 5,000 limit never fire?
2. Run C used fewer input tokens but cost more. Why?
3. What would the briefing need to contain for the model to skip the re-read?

**Our result:** see [outputs/stage4/comparison.md](../outputs/stage4/comparison.md).
