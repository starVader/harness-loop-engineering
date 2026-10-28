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

## The outer loop (written)
| File | What it does |
|---|---|
| `reflect.py propose` | one call to Opus. It reads only `runs/stage8/train-*` (transcripts, accepted diffs, audit incidents) plus `INTENT.md` and `LESSONS.md`, and writes `runs/stage8/proposals.md`. Each proposal is an **intent rule** (a business rule, in business words) or a **lesson** (how to work), with its evidence and why it should transfer |
| `reflect.py gate` | the stage 7 gate applied to proposals: one sentence to accept each one, or `reject: <why>`. Decisions go to `runs/stage8/decisions.md`; accepted rules are appended to `INTENT.md`, lessons to `LESSONS.md` |
| `loop.py --lessons` | appends `LESSONS.md` to the actor's system prompt, if the file exists. The actor can't open it with a tool |
| `stage8/run.py PHASE` | runs every bug set in a phase and saves `<phase>-<NN>.md/.diff/.audit/.progress.json`; `summary` tabulates them |

**The reflector's limits.** It proposes; it never applies. Only `reflect.py
gate`, with your sentence, changes `INTENT.md` or `LESSONS.md`. It can't
touch tests, `tools.py`, `goal.py` or the audit: a learner that can edit its
own oracle learns to grade itself (stage 2, one level up).

**Why the gate is off for the loop runs.** `run.py` passes `--no-gate`. If
you explained every fix, you would catch the bugs yourself, and the
experiment would measure you, not what the harness learned. Here the human
gate guards what gets *learned*, not what gets merged.

## Steps
The actor is Haiku throughout: stage 6 showed Sonnet rarely takes a shortcut,
which leaves nothing to learn. `run.py` refuses a `before` or `train` phase
once `INTENT.md` or `LESSONS.md` has changed, so the order can't be mixed up.

1. **Before: held-out baseline.** `venv/bin/python stage8/run.py before`.
   This also freezes `runs/stage8/intent_before.md`. It shows what the
   harness does with no learning. The reflector never sees it.
2. **Train.** `venv/bin/python stage8/run.py train`. The audit incidents are
   the "complaints" the outer loop gets to learn from.
3. **Reflect.** `venv/bin/python reflect.py propose`, then read
   `runs/stage8/proposals.md`.
4. **Gate.** `venv/bin/python reflect.py gate`. Reject any proposal that
   names a file, a function or a bug set: an accountant wouldn't understand
   it, and it won't transfer.
5. **After: held-out again.** `venv/bin/python stage8/run.py after`.
6. **Overfitting check.** `venv/bin/python stage8/run.py retrain`. If train
   incidents fall and held-out ones don't, the outer loop memorised.
7. **Compare.** `venv/bin/python stage8/run.py summary` writes
   `runs/stage8/summary.md`.

Runs vary: if your budget allows, run `before` and `after` twice (rename the
first set of files) and report both. Three held-out bug sets is a small
sample, so report counts, not percentages. The audit only means something
for an `accepted` run; the summary shows each run's outcome next to its
incidents.

## Possible outcomes
| Held-out incidents, before → after | Train incidents, train → retrain | What it shows |
|---|---|---|
| fall | fall | learning that transfers: the rules were about the business, not the bugs |
| flat | fall | memorisation: the lessons fit 01-03 and nothing else |
| flat (0 → 0) | flat (0 → 0) | Haiku fixed everything honestly; nothing to learn, like stage 6 |
| rise | any | a learned rule misled the actor or the checker: the gate let a bad one through |

Also watch *how* the incidents fell. Did the actor avoid the shortcut (the
rule steered it), or take it and get `CHECKER REJECTED` (the rule was
enforced)? That's the same steer-versus-guard question as stage 6.

## Save to `outputs/stage8/`
Everything in `runs/stage8/` (`intent_before.md`, `proposals.md`,
`decisions.md`, `summary.md`, every run's `.md`, `.diff` and `.audit`), the
learned `INTENT.md` and `LESSONS.md`, a `comparison.md` in your words, and
your `notes.md`.

## Questions for your notes
1. Which accepted proposal did the most work, and on which held-out bug set?
2. Did you reject anything? Would accepting it have helped train and hurt
   held-out?
3. Which incidents survived learning? Was the reflector missing evidence, or
   was the rule there and still ignored?
4. What stops this outer loop from running unattended every night? (Stage 9
   is where you'll be tempted.)
