# Exercises

One file per stage. Work through them in order; each one builds on the last.

## How every stage works
1. Read `stageN.md`.
2. Reset the code: `git restore --source=broken -- checkout/`
3. Write or change your code (`goal.py`, `loop.py`, `spine.py`).
4. Run it. Raw output goes to `runs/` (gitignored).
5. Copy the run worth keeping into `../outputs/stageN/` (see [outputs/README.md](../outputs/README.md)).
6. Write `outputs/stageN/notes.md`: what happened, in your words.
7. Commit.

## Stages
| Stage | What you learn | Exercise |
|---|---|---|
| 1 | The bare loop: act, observe, adjust | [stage1.md](stage1.md) |
| 2 | A vague goal vs a goal code can check | [stage2.md](stage2.md) |
| 3 | The spine: memory across runs | [stage3.md](stage3.md) |
| 4 | Context: fresh vs growing, compaction | [stage4.md](stage4.md) |
| 5 | A checker on a different model | [stage5.md](stage5.md) |
| 6 | Intent debt: the trap in bug 4 | [stage6.md](stage6.md) |
| 7 | The human gate | coming |
| 8 | The outer loop: learning from past runs | [stage8.md](stage8.md) |
| 9 | Triggers: schedule and hook | coming |

Diagrams: [stage 0 scaffold](../assets/stage0_scaffold.png) · stage flows [1](../assets/stage1_flow.png) [2](../assets/stage2_flow.png) [3](../assets/stage3_flow.png) [4](../assets/stage4_flow.png) [5](../assets/stage5_flow.png) [6](../assets/stage6_flow.png) · [final architecture](../assets/final_architecture.png)
