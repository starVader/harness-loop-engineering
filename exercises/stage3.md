# Stage 3: the spine, memory that survives a crash

![Stage 3 flow](../assets/stage3_flow.png)

**You learn:** when a run dies, the conversation dies with it. Only what you
wrote to disk survives, and what you choose to write decides how well the
next run can continue.

**You build:** `spine.py` (save and load `progress.json`), the spine wired
into `loop.py`, and two flags: `--fresh` and `--stop-after N`.

## What goes in the spine
Store what was **learned**, not what was **read**:

| Store | Don't store |
|---|---|
| tools called each pass (names + paths) | file contents |
| files written | the full conversation |
| failing test ids after each pass | |
| status: `running` / `done` / `stopped` | |
| a fingerprint (hash) of `checkout/` | |

The model can always re-read a file. It can't recover a decision.

## Rules the loop enforces
| Spine says | Loop does | Why |
|---|---|---|
| `done` | ALREADY DONE: exit, no API call | idempotency: a rerun must not repeat effects |
| `stopped` | refuse; use `--fresh` | a failed run isn't silently retried |
| fingerprint ≠ code | STALE SPINE: start fresh | a record that no longer matches reality is a lie |
| `running` | resume at the next pass number | crash recovery |

The pass cap counts **all** passes across resumes, so a crash can't reset the budget.
Save after every pass, atomically (temp file + `os.replace`), so a crash mid-save can't corrupt it.

## Steps
1. Write `spine.py`: `PassRecord`, `Spine`, `load_spine()` (an unreadable file
   means no spine, never a crash), `save_spine()` (atomic), `fingerprint_code()`,
   `failing_tests_from()`, `progress_note()` (the resume briefing).
2. In `loop.py`: decide resume vs fresh at start; append the briefing to the
   task on resume; save a `PassRecord` after every round of tools; mark `done`
   or `stopped` at the end; add `--fresh` and `--stop-after`.
3. Check every path with a stub first (no tokens): crash, resume, done,
   stale, corrupt, cap.
4. Predict before running: will the resumed model skip discovery? Will it
   re-read files? How big will its first call be?
5. Run:
   ```
   git restore --source=broken -- checkout/ && venv/bin/python loop.py --fresh --stop-after 2 | tee runs/stage3-crash.md && cp progress.json runs/stage3-progress-after-crash.json
   venv/bin/python loop.py | tee runs/stage3-resume.md      # no reset in between
   venv/bin/python loop.py                                  # expect ALREADY DONE
   ```

## Save to `outputs/stage3/`
`run_crash.md`, `run_resume.md`, `progress_after_crash.json`,
`progress_final.json`, `diff.patch`, `tokens.csv`, `comparison.md`, your `notes.md`.

## Questions for your notes
1. What did the resumed model skip, and what did it have to redo? Why?
2. What would have happened if you had reset `checkout/` between the crash and
   the resume, without the fingerprint check?
3. Why was the crash + resume cheaper than one uninterrupted run?

**Our result:** see [outputs/stage3/comparison.md](../outputs/stage3/comparison.md).
