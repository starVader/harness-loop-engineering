# Exercises

One guide per layer. Each one has the same shape:

- **The idea**: what the layer is for, in a few sentences.
- **In the code**: where it lives, so you can read it next to the guide.
- **Run it**: the exact commands, with the later layers switched off so this one stands alone.
- **What happened when we ran it**: the recorded result in [results/](../results/).
- **Try this**: experiments that change one thing and show why the layer exists.

Every run starts from a known state: `python -m harness.scenario apply broken`
puts back the 4 bugs (it won't overwrite edits of your own without `--force`).
Every run also leaves a trace: `python -m harness.trace show latest`.

| Stage | Guide | Flowchart |
|---|---|---|
| 0 | [The playground: tools, guardrails, scenarios](stage0.md) | [scaffold](../assets/stage0_scaffold.png) |
| 1 | [The bare loop](stage1.md) | [flow](../assets/stage1_flow.png) |
| 2 | [Who decides "done"?](stage2.md) | [flow](../assets/stage2_flow.png) |
| 3 | [The spine: memory that survives a crash](stage3.md) | [flow](../assets/stage3_flow.png) |
| 4 | [Context: forgetting on purpose](stage4.md) | [flow](../assets/stage4_flow.png) |
| 5 | [The checker: a second model reviews the work](stage5.md) | [flow](../assets/stage5_flow.png) |
| 6 | [Intent debt: the rule nobody wrote](stage6.md) | [flow](../assets/stage6_flow.png) |
| 7 | [The human gate](stage7.md) | [flow](../assets/stage7_flow.png) |
| 8 | [The outer loop: learning from past runs](stage8.md) | [flow](../assets/stage8_flow.png) |

The layers are cumulative but the guides aren't: you can jump straight to
any stage. Stages 1-4 need only an API key. Stages 7-8 need you at the
keyboard.
