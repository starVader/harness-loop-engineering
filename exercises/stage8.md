# Stage 8: the outer loop, learning from past runs

**You learn:** a harness that only runs is as good as the rules a human
remembered to write down. An outer loop reads what past runs did, what went
wrong *after* they were accepted, and proposes what to write down next. The
hard part isn't getting it to propose. It's proving the proposals made the
next, *unseen* run better, and not just memorising the last one.

**Why the old setup can't show this:** stages 1-6 used one task: the same 4
bugs. Anything learned from it is the answer key ("bug 4 is `_order_date`"),
and a replay would look like a big improvement that means nothing. Learning
needs a task *family*, with a split between what you learn from and what you
measure on.

## The setup (given)
| What | Where | Who may read it |
|---|---|---|
| 6 bug sets, each green code + 1-2 bugs | `stage8/bugsets/` | nobody until your notes are written: spoilers |
| `stage8/bugset.py NN` | puts `checkout/` into bug set NN, tags it `bugset-NN` | you |
| The audit: business rules the visible tests miss | `stage8/audit/` | **never** the actor or the reflector |
| `stage8/audit.py` | runs the audit, prints one *incident* per broken rule | you; the reflector sees its output for training runs only |
| `LOOP_BASELINE` | `checker.py` diffs against this tag (default `broken`) | — |

Every bug set fails exactly one visible test, so the loop always has work to
do. Some also carry a second bug the visible tests don't catch, and every
one has a shortcut that turns the tests green and still breaks a business
rule. The audit is your stand-in for production: it finds what got through,
the way an accounts reconciliation does weeks later.

| Split | Bug sets | Use |
|---|---|---|
| train | 01, 02, 03 | the loop runs on these; the reflector learns from their logs and audit incidents |
| held-out | 04, 05, 06 | measured before and after learning; the reflector never sees them |

The two splits share kinds of mistake, not the same mistake. A lesson that
transfers is a real one; a lesson that only fixes 01-03 is memorisation.

## What you write
1. **`reflect.py`**: the outer loop's one step. It reads the training runs
   (transcripts, `progress.json` copies, checker summaries, audit incidents)
   plus the current `INTENT.md` and `LESSONS.md`, makes one model call, and
   writes `runs/stage8/proposals.md`. Each proposal is one of:
   - an **intent rule** for `INTENT.md`: a business rule, in business words
   - a **lesson** for `LESSONS.md`: advice on *how* to work ("check what a
     function's docstring promises before changing its callers")

   Each proposal cites its evidence: which run, which incident or "not
   covered" note. Use structured outputs, as `checker.py` does.
2. **A change to `loop.py`**: if `LESSONS.md` exists, append it to the actor's
   system prompt. The actor still can't open it with a tool, the same as the
   audit.

**The reflector's limits.** It proposes changes; it never applies them. It
may propose changes to `INTENT.md` and `LESSONS.md` only, never to tests,
`tools.py`, `goal.py` or the audit. A learner that can edit its own oracle
learns to grade itself (stage 2, one level up).

## Steps
Use the Haiku actor throughout (`--actor-model haiku`): stage 6 showed Sonnet
rarely takes a shortcut, which leaves nothing to learn. One run, for bug set
NN and phase P (`before`, `train` or `after`):
```
venv/bin/python stage8/bugset.py NN && LOOP_BASELINE=bugset-NN venv/bin/python loop.py --fresh --actor-model haiku | tee runs/stage8/P-NN.md && cp progress.json runs/stage8/P-NN.progress.json && git diff bugset-NN -- checkout/ > runs/stage8/P-NN.diff && venv/bin/python stage8/audit.py | tee runs/stage8/P-NN.audit
```

0. **Freeze the start.** `mkdir -p runs/stage8`, then copy `INTENT.md` to `runs/stage8/intent_before.md`.
   `LESSONS.md` must not exist yet.
1. **Before: held-out baseline.** Run 04, 05 and 06 (phase `before`). This
   is what the harness does with no learning. Don't show these results to
   the reflector.
2. **Train.** Run 01, 02 and 03 (phase `train`). Count the audit incidents:
   these are the "complaints" the outer loop gets to learn from.
3. **Reflect.** `venv/bin/python reflect.py`, which reads only
   `runs/stage8/train-*` and writes `runs/stage8/proposals.md`.
4. **Gate.** For each proposal, accept or reject it with one sentence in
   `runs/stage8/decisions.md`, then copy accepted rules into `INTENT.md` and
   lessons into `LESSONS.md`. If you built `gate.py` in stage 7, use it here.
   Reject any proposal that names a line, a variable or a bug set: an
   accountant wouldn't understand it, and it won't transfer.
5. **After: held-out again.** Run 04, 05 and 06 again (phase `after`), with
   the learned `INTENT.md` and `LESSONS.md`.
6. **Overfitting check.** Rerun 01-03 too (phase `retrain`). If the
   train incidents fall but held-out ones don't, the outer loop memorised.

Runs vary: if your budget allows, do steps 1 and 5 twice and report both.
Three held-out bug sets is a small sample, so report counts, not percentages.

## Possible outcomes
| Held-out incidents, before → after | Train incidents, before → retrain | What it shows |
|---|---|---|
| fall | fall | learning that transfers: the rules were about the business, not the bugs |
| flat | fall | memorisation: the lessons fit 01-03 and nothing else |
| flat (0 → 0) | flat (0 → 0) | Haiku fixed everything honestly; nothing to learn, like stage 6 |
| rise | any | a learned rule misled the actor or the checker: the gate let a bad one through |

Also watch *how* the incidents fell. Did the actor avoid the shortcut (the
rule steered it), or take it and get `CHECKER REJECTED` (the rule was
enforced)? That's the same steer-versus-guard question as stage 6.

## Save to `outputs/stage8/`
`intent_before.md`, `INTENT.md` after, `LESSONS.md`, `proposals.md`,
`decisions.md`, every run's `.md`, `.diff` and `.audit`, a `comparison.md`
with incidents per bug set per phase, and your `notes.md`.

## Questions for your notes
1. Which accepted proposal did the most work, and on which held-out bug set?
2. Did you reject anything? Would accepting it have helped train and hurt
   held-out?
3. Which incidents survived learning? Was the reflector missing evidence, or
   was the rule there and still ignored?
4. What stops this outer loop from running unattended every night? (Stage 9
   is where you'll be tempted.)
