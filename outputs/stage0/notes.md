# Stage 0 notes

- `tests_green.txt`: the scaffold before any bugs, 14 passed.
- `tests_broken.txt`: after `stage0/inject_bugs.patch`, 4 failed, 10 passed. Each bug breaks exactly one test.
- `guardrail_check.txt`: what `execute_tool` returns for allowed and blocked requests. Only `checkout/*.py` is writable.

Takeaway: the harness is built before the loop. The model can only change product code, and only the tests decide "done".
