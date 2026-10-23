# Stage 3: crash and resume with the spine

Same model (Sonnet 5.5), system prompt, tools and `--goal pytest` as stage 2
run B. Run 1 crashed on purpose (`--stop-after 2`); run 2 resumed from
`progress.json` without resetting the code; run 3 reran the finished goal.

## What each run did
| Run | Passes | Model's moves | Ended |
|---|---|---|---|
| 1 crash | 1-2 | `list_files` + `run_tests`; then read 7 files | SIMULATED CRASH, spine `running` |
| 2 resume | 3-4 | "I no longer have the file contents, so I'll re-read them": read 6 files; then wrote `discounts.py` + `checkout.py` | DONE: goal verified on pass 4 |
| 3 rerun | none | no API call | ALREADY DONE (no-op) |

Raw output: [run_crash.md](run_crash.md), [run_resume.md](run_resume.md).
Spine after the crash: [progress_after_crash.json](progress_after_crash.json);
final: [progress_final.json](progress_final.json). Fixes: [diff.patch](diff.patch)
(the same 4 fixes as stages 1 and 2). Per-pass tokens: [tokens.csv](tokens.csv).

## Predictions vs result
| Prediction | Result |
|---|---|
| Resume skips `list_files` and `run_tests` | yes: the briefing listed the failing tests and the files read |
| Resume must re-read the files | yes, and the model said so itself |
| First resumed call is small (~1,200 tokens) | 1,211, vs 5,929 for stage 2 run B's pass 3 |

## What the spine kept and lost
| Kept: decisions and facts | Lost: raw material |
|---|---|
| the 4 failing test ids | the assertion messages |
| which files were relevant | what is in those files |
| nothing changed yet | the model's diagnosis of each bug |

## Bonus: the interrupted job was cheaper
| | Input | Output | Passes |
|---|---|---|---|
| Stage 2 run B (no crash) | 15,627 | 2,156 | 4 |
| Stage 3 crash + resume | 3,228 + 5,649 = 8,877 | 413 + 2,096 = 2,509 | 2 + 2 |

About 43% less input: the restart dropped the old history, so passes 1-2's
file contents were never re-sent. It paid a re-read (slightly more output).
That is compaction by accident; stage 4 does it on purpose. One run each, and
run B spent an extra pass reading `cart.py`, so the direction is solid but
the exact percentage is not.

## Properties proven
1. A crash loses at most the current pass (spine saved after every pass, atomically).
2. Resume continues: discovery skipped, pass numbers continue, one shared cap of 8.
3. A finished job reruns as a no-op: idempotency.

Also proven with a scripted stub (no tokens): a spine whose code fingerprint
no longer matches is discarded (STALE SPINE), a corrupt `progress.json` is
ignored rather than crashing, and the 8-pass cap holds across resumes.
