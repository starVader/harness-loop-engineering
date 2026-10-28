# Loop Engineering Lab

Hands-on rebuild of the loop from IBM Technology's *What Is Loop Engineering?*:
**goal (verifiable stop) → act → observe → adjust → repeat**, plus the things
built around it — spine, context, checker, intent, human gate, learning, triggers.

The system under repair is a tiny checkout service with 4 injected bugs. You
write the loop; the tests are the oracle.

## Setup (once)
```
python3 -m venv venv && venv/bin/pip install -r requirements.txt
git add -A && git commit -m "green checkout"
git apply stage0/inject_bugs.patch && git commit -am "inject 4 bugs" && git tag broken
```
Reset the code between runs: `git restore --source=broken -- checkout/`. This puts only `checkout/` back to the 4 bugs; your `loop.py`, outputs and commits stay. Never `git reset --hard broken` once you have commits after the tag: it moves `main` back and drops them.

## Where things live
| Folder | What |
|---|---|
| `exercises/` | one file per stage: the task, steps, and pass condition. Start at [exercises/README.md](exercises/README.md) |
| `outputs/` | the evidence from each stage's run, committed. See [outputs/README.md](outputs/README.md) |
| `assets/` | diagrams |
| `runs/` | raw output from every run, gitignored |

## Who writes what
| File | Author |
|---|---|
| `checkout/`, `tests/`, `tools.py`, `INTENT.md` | given (stage 0) |
| `goal.py`, `loop.py`, `spine.py` | **you** (stages 1-6) |
| `checker.py`, `gate.py` | given as references at stages 5 and 7 |
| `reflect.py`, `stage8/` (bug sets, audit, runner) | given at stage 8 |

`tools.py` exposes `TOOLS` (Anthropic tool schemas) and `execute_tool(name, input) -> ToolOutcome`.
The actor can write only `checkout/*.py`; `run_tests` has a fixed invocation. Use `tools.run_tests()` directly as your oracle.

## Stages
1. **Bare loop** — `messages.create` with `TOOLS`; run every `tool_use`, return all `tool_result`s in one user message; cap at 8 iterations.
2. **Bad goal vs oracle** — `SelfAssessedGoal` (model says DONE, `is_met()` → `None`) vs `PytestGoal` (`run_tests().exit_code == 0`).
3. **Spine** — persist attempts + per-test outcome; Ctrl-C and restart; it must not redo green work.
4. **Context** — fresh context + spine vs one growing conversation; hand-roll compaction past ~20K tokens; log `usage.input_tokens` per pass.
5. **Checker** — Haiku reviews `git diff broken` against `INTENT.md`; a fail feeds back into the loop.
6. **Intent debt** — run without a discount rule in `INTENT.md`, then with one. Watch what the actor does to the expiry check.
7. **Human gate** — no pass is accepted without your one-sentence explanation in `outputs/stage7/fixes.md`.
8. **Outer loop** — `reflect.py` reads past runs and audit incidents, proposes `INTENT.md` rules and `LESSONS.md`; you gate them. Learn on bug sets 01-03, measure on unseen 04-06.
9. **Triggers** — nightly cron in a *separate clone*; a git post-commit hook.

## Lab rules
- Don't read `stage0/inject_bugs.patch` before stage 6 — it spoils the trap.
- Don't read `stage8/bugsets/` or `stage8/audit/` before your stage 8 notes are written.
- The tests deliberately do **not** cover every business rule. That gap is the point of stages 5–6.
