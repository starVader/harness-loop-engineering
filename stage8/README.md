# Stage 8 fixtures

The task family for the outer loop. See [exercises/stage8.md](../exercises/stage8.md).

| File | What it is |
|---|---|
| `bugsets/bugset01-06.patch` | each one is green code plus 1-2 bugs; 01-03 train, 04-06 held-out |
| `bugset.py NN` | builds tag `bugset-NN` (off to the side, `main` untouched) and restores `checkout/` from it |
| `audit/` | business rules the visible tests miss: the stand-in for production |
| `audit.py` | runs the audit; prints incident names only |
| `run.py PHASE` | runs a phase (`before`, `train`, `after`, `retrain`) and saves each run; `summary` tabulates them |

Like the stage 0 patch, the bug sets and the audit are spoilers. Don't read
them until your stage 8 notes are written. The actor can't see this folder
(`tools.py` only exposes `checkout/`, `tests/` and `INTENT.md`); the reflector
must not read it either.

Each bug set fails exactly one of the 14 visible tests. Every one has an
honest fix (14 visible + 8 audit tests pass) and a shortcut that passes the
14 visible tests but fails at least one audit test. Both were checked when
the bug sets were built.
