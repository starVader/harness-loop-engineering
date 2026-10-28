# How this repo maps to published practice

Harness engineering is young, but the main sources agree on a short list of
practices. This table shows where each one lives in this repo, so you can read
the source and the code side by side. Compiled October 2026; where a source
couldn't be fetched directly, the coverage used is linked instead.

| Practice | Sources | Where it is here |
|---|---|---|
| A goal code can check; a convincing final message is not evidence | [IBM][ibm], [Arize][arize], [Anthropic evals][evals] | Stage 2: `PytestGoal`, the loop stops on the tests ([goal.py](harness/goal.py)) |
| Authority lives in code: what the agent may touch, see and call | [Arize][arize], [Anthropic: building effective agents][bea] | Stage 0: tool allowlist, writes only to `checkout/*.py`, fixed `run_tests` ([tools.py](harness/tools.py)) |
| Run untrusted, agent-written code in a sandbox | [Anthropic: building effective agents][bea], [Orchestra][orchestra], [SafeHarness][safeharness] | `--sandbox docker`: no network, read-only code, capped resources ([sandbox.py](harness/sandbox.py)) |
| Iteration, cost and time limits enforced by the runtime; escalate when they run out | [Arize][arize], [Orchestra][orchestra], [Anthropic: building effective agents][bea] | Budgets → `ESCALATED` ([budget.py](harness/budget.py), `escalate` in [loop.py](harness/loop.py)) |
| A progress file read at startup, so a new context can resume | [Anthropic: long-running agents][long], [IBM][ibm] | Stage 3: the spine ([spine.py](harness/spine.py)) |
| Treat context as a budget: compaction, resets, structured notes | [Anthropic: context engineering][context], [Anthropic: harness design][design] | Stage 4: `compact_history` from the spine, measured in money ([loop.py](harness/loop.py)) |
| A separate reviewer instead of self-checking; tune it to be skeptical | [IBM][ibm], [Anthropic: harness design][design] | Stage 5: a different model, typed verdict, fails closed ([checker.py](harness/checker.py)) |
| Deterministic sensors before inferential ones; messages that tell the agent how to fix | [Fowler/Böckeler][fowler], [OpenAI via InfoQ][openai] | Fixed rules before the checker ([sensors.py](harness/sensors.py)) |
| Test the grader: known cases, multiple trials, pass^k | [Anthropic evals][evals] | Checker eval ([checker_eval.py](harness/checker_eval.py), [expected.json](scenarios/cheats/expected.json)) |
| Write intent down (AGENTS.md-style feedforward guides) | [IBM][ibm], [Fowler/Böckeler][fowler], [OpenAI via InfoQ][openai] | Stage 6: [INTENT.md](INTENT.md), `--intent` |
| Keep a human accountable; watch for comprehension debt | [IBM][ibm], [Fowler/Böckeler][fowler] | Stage 7: the gate ([gate.py](harness/gate.py)) |
| Keep quality left: cheap checks first, expensive ones later | [Fowler/Böckeler][fowler] | `review_change`: tests → fixed rules → checker → human |
| Trace every model call, tool call, verdict and approval against one run | [Arize][arize], [Orchestra][orchestra] | JSON-lines trace per run ([trace.py](harness/trace.py)) |
| Improve the harness when a failure recurs (the steering loop) | [Fowler/Böckeler][fowler], [deepset][deepset] | Stage 8: the reflector, through a human gate ([reflect.py](harness/reflect.py)) |
| Learn on one set, measure on another; grade outcomes, not paths | [Anthropic evals][evals] | Stage 8: train/held-out bug sets, the audit as outcome grader ([experiment.py](harness/experiment.py)) |
| Every harness piece assumes a model weakness; remove pieces one at a time to test it | [Anthropic: harness design][design] | Every layer has an off switch (`--no-check`, `--no-sensors`, `--no-gate`, `--no-compact`) |
| Start simple; add agents only when a limit appears | [Anthropic: building effective agents][bea] | One actor loop; the checker and reflector are single calls with no tools |

## Not covered, on purpose

- **Subagents and multi-agent planners** ([Anthropic: harness design][design], [IBM][ibm]). The task fits one context; "start simple" wins.
- **Agent-written architecture rules and garbage collection** ([OpenAI via InfoQ][openai]). They pay off in large codebases, not a four-file service.
- **Multiple trials of the main loop.** The checker eval reports pass^k; stage 8 suggests running phases twice but doesn't automate it.

[ibm]: https://www.ibm.com/think/topics/loop-engineering
[arize]: https://arize.com/resources/harness-engineering/
[evals]: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
[bea]: https://www.anthropic.com/engineering/building-effective-agents
[long]: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
[context]: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
[design]: https://www.anthropic.com/engineering/harness-design-long-running-apps
[fowler]: https://martinfowler.com/articles/harness-engineering.html
[openai]: https://www.infoq.com/news/2026/02/openai-harness-engineering-codex
[orchestra]: https://www.getorchestra.io/guides/ai-harness-engineering
[deepset]: https://www.deepset.ai/blog/harness-engineering
[safeharness]: https://arxiv.org/pdf/2604.13630
