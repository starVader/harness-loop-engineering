"""Stage 1-4 loop flowcharts, matching loop.py at each stage's commit."""

import sys

from flowgen import COL_X, Node, ROW_H, TOP, edge, render

OUT = sys.argv[1]
LANE_X = 290  # back-edge lane, left of the main column


def nodes_from(specs):
    return {spec[0]: Node(*spec) for spec in specs}


def yes_no_down(a, b, label="no", label_left=False):
    if label_left:
        return edge([a.bottom(), b.top()], label, label_at=(a.x - 8, a.y + a.h / 2 + 13), anchor="end")
    return edge([a.bottom(), b.top()], label)


def right_to(a, b, label="yes"):
    return edge([a.right(), b.left()], label, label_at=(a.right()[0] + 8, a.y - 8))


def back_to(a, b, label="yes"):
    (ax, ay), (bx, by) = a.left(), b.left()
    return edge([(ax, ay), (LANE_X, ay), (LANE_X, by), (bx, by)], label, label_at=(LANE_X - 8, (ay + by) / 2), anchor="end")


def height_for(rows, result_lines):
    return TOP + rows * ROW_H + 40 + 20 * result_lines + 40


# ---------------------------------------------------------------- stage 1
n = nodes_from([
    ("start", 0, 0, "Start\nmessages = [TASK]", "term", "term"),
    ("call", 0, 1, "Act: call the model\nmessages + tools", "box", "new"),
    ("tooluse", 0, 2, "stop_reason == tool_use?", "diamond", "plain"),
    ("tools", 0, 3, "Observe: run every tool\nall tool_results in one message", "box", "new"),
    ("goal", 0, 4, "Goal: run_tests() == 0?", "diamond", "new"),
    ("cap", 0, 5, "pass < 8?", "diamond", "plain"),
    ("stopped", 1, 2, "Model stopped\nrun_tests(): DONE or\nSTOPPED EARLY", "term", "term"),
    ("done", 1, 4, "DONE\ngoal verified by code", "term", "done"),
    ("caphit", 1, 5, "CAP HIT\nnever loop forever", "term", "bad"),
])
e = [
    edge([n["start"].bottom(), n["call"].top()]),
    edge([n["call"].bottom(), n["tooluse"].top()]),
    yes_no_down(n["tooluse"], n["tools"], "yes"),
    right_to(n["tooluse"], n["stopped"], "no"),
    edge([n["tools"].bottom(), n["goal"].top()]),
    right_to(n["goal"], n["done"]),
    yes_no_down(n["goal"], n["cap"]),
    right_to(n["cap"], n["caphit"], "no"),
    back_to(n["cap"], n["call"], "yes: next pass (Adjust)"),
]
res = ["Result: goal met on pass 3 of 8. Your code ended the run, not the model.",
       "Pass 1 run_tests + list_files · pass 2 read 8 files · pass 3 wrote 2 files → 14 passed",
       "Tokens 9,511 in / 2,152 out. Lesson: the model proposes; code checks and decides done."]
render(f"{OUT}/stage1_flow.svg", "Stage 1: the bare loop", "Act → observe → goal check, repeated until the tests pass or the cap is hit.",
       n, e, "new in this stage", res, height_for(6, len(res)))

# ---------------------------------------------------------------- stage 2
n = nodes_from([
    ("start", 0, 0, "Start: --goal pytest | self\ntask = template(goal.description)", "term", "new", 300),
    ("call", 0, 1, "Act: call the model", "box", "model"),
    ("tooluse", 0, 2, "stop_reason == tool_use?", "diamond", "plain"),
    ("tools", 0, 3, "Observe: run every tool", "box", "plain"),
    ("goal", 0, 4, "goal.is_met()?", "diamond", "new"),
    ("cap", 0, 5, "pass < 8?", "diamond", "plain"),
    ("observer", 0, 6, "Every exit → observer\nruns the tests once more", "box", "new", 280),
    ("stopped", 1, 2, "Model claims done:\nNone → ACCEPTED ON ITS WORD\nTrue → DONE · False → EARLY", "term", "new", 270),
    ("done", 1, 4, "True → DONE\nverified by code", "term", "done"),
    ("caphit", 1, 5, "CAP HIT", "term", "bad"),
])
e = [
    edge([n["start"].bottom(), n["call"].top()]),
    edge([n["call"].bottom(), n["tooluse"].top()]),
    yes_no_down(n["tooluse"], n["tools"], "yes"),
    right_to(n["tooluse"], n["stopped"], "no"),
    edge([n["tools"].bottom(), n["goal"].top()]),
    right_to(n["goal"], n["done"], "True"),
    yes_no_down(n["goal"], n["cap"], "False, or None (can't check)"),
    right_to(n["cap"], n["caphit"], "no"),
    back_to(n["cap"], n["call"], "yes"),
]
res = ["Result: both goals fixed all 4 bugs (14 passed): the system prompt carried the real goal.",
       "self:   5 passes · 25,306 in / 2,848 out · ended ACCEPTED ON THE MODEL'S WORD (right, but unverifiable)",
       "pytest: 4 passes · 15,627 in / 2,156 out · ended DONE: goal verified on pass 4",
       "Lesson: is_met() returning None means code must trust the model; it cost 62% more input."]
render(f"{OUT}/stage2_flow.svg", "Stage 2: who decides \"done\"?", "The same loop with a pluggable goal. A goal code can't check returns None.",
       n, e, "new in this stage", res, height_for(7, len(res)))

# ---------------------------------------------------------------- stage 3 and 4 share the spine layout
def spine_stage(compaction):
    specs = [
        ("start", 0, 0, "Start: --fresh? --stop-after N?", "term", "term", 300),
        ("open", 0, 1, "open_spine(): read progress.json\nstale fingerprint → fresh · running → resume", "box", "plain" if compaction else "new", 340),
        ("call", 0, 2, "Act: call the model\n(on resume: task + briefing)", "box", "model"),
        ("tooluse", 0, 3, "stop_reason == tool_use?", "diamond", "plain"),
        ("tools", 0, 4, "Observe: run every tool", "box", "plain"),
        ("record", 0, 5, "Record the pass in the spine\ntools · files written · failing tests", "box", "plain" if compaction else "new", 300),
        ("goal", 0, 6, "goal.is_met()?", "diamond", "plain"),
        ("save", 0, 7, "Save progress.json\natomic: temp file + os.replace", "box", "plain" if compaction else "new", 280),
    ]
    row = 8
    if compaction:
        specs.append(("compact", 0, row, "last call > compact_at?", "diamond", "new"))
        specs.append(("compacted", 1, row, "COMPACTED\nmessages = task + briefing", "box", "new", 240))
        row += 1
    specs += [
        ("crash", 0, row, "--stop-after reached?", "diamond", "plain" if compaction else "new"),
        ("cap", 0, row + 1, "passes < 8 (all runs)?", "diamond", "plain" if compaction else "new"),
        ("refused", 1, 1, "Already finished:\ndone → ALREADY DONE\nstopped → refused", "term", "bad", 220),
        ("stopped", 1, 3, "Model stopped\nspine: done / stopped", "term", "term", 220),
        ("done", 1, 6, "DONE\nspine status = done", "term", "done", 220),
        ("crashed", 1, row, "SIMULATED CRASH\nspine stays running", "term", "bad", 220),
        ("caphit", 1, row + 1, "CAP HIT\nspine status = stopped", "term", "bad", 220),
    ]
    n = nodes_from(specs)
    e = [
        edge([n["start"].bottom(), n["open"].top()]),
        edge([n["open"].right(), n["refused"].left()]),
        edge([n["open"].bottom(), n["call"].top()], "fresh or resume"),
        edge([n["call"].bottom(), n["tooluse"].top()]),
        yes_no_down(n["tooluse"], n["tools"], "yes"),
        right_to(n["tooluse"], n["stopped"], "no"),
        edge([n["tools"].bottom(), n["record"].top()]),
        edge([n["record"].bottom(), n["goal"].top()]),
        right_to(n["goal"], n["done"], "True"),
        yes_no_down(n["goal"], n["save"], "False / None"),
        right_to(n["crash"], n["crashed"]),
        yes_no_down(n["crash"], n["cap"]),
        right_to(n["cap"], n["caphit"], "no"),
        back_to(n["cap"], n["call"], "yes"),
    ]
    if compaction:
        c, cd = n["compact"], n["compacted"]
        merge_y = c.y + c.h / 2 + 14
        e += [
            edge([n["save"].bottom(), c.top()]),
            right_to(c, cd),
            edge([cd.bottom(), (cd.x, merge_y), (COL_X[0] + 6, merge_y)], color="#D85A30"),
            yes_no_down(c, n["crash"], label_left=True),
        ]
    else:
        e.append(edge([n["save"].bottom(), n["crash"].top()]))
    return n, e, row + 2


n, e, rows = spine_stage(compaction=False)
res = ["Result: crash after 2 passes → resume finished on pass 4 → rerun printed ALREADY DONE.",
       "On resume the model skipped discovery but said \"I no longer have the file contents\" and re-read 6 files.",
       "Crash + resume: 8,877 in / 2,509 out vs 15,627 in for one uninterrupted run: the restart dropped old history.",
       "Lesson: the spine keeps decisions, not contents. Done = no-op (idempotent); a stale spine is discarded."]
render(f"{OUT}/stage3_flow.svg", "Stage 3: the spine, memory that survives a crash", "Every pass is saved to progress.json, so a new process can resume instead of restart.",
       n, e, "new in this stage", res, height_for(rows, len(res)))

n, e, rows = spine_stage(compaction=True)
res = ["Result: all 3 runs fixed the 4 bugs. Compaction cut input tokens but raised the bill.",
       "A, limit 5,000: never fired (the run ended first) · 3 passes · 9,157 in / 2,252 out · $0.041",
       "B, --no-compact: baseline · 3 passes · 9,418 in / 2,264 out · $0.042",
       "C, limit 2,000: fired after the file read, then a re-read pass · 4 passes · 8,876 in / 2,562 out · $0.043",
       "Lesson: forgetting right after learning forces a re-read; output costs 5x input; a size check lags one call."]
render(f"{OUT}/stage4_flow.svg", "Stage 4: compaction, forgetting on purpose", "When the last call was too big, restart the conversation from the spine's briefing.",
       n, e, "new in this stage", res, height_for(rows, len(res)))
print("ok")

# ---------------------------------------------------------------- stage 5: the acceptance path
def left_to(a, b, label):
    return edge([a.left(), b.right()], label, label_at=(a.left()[0] - 8, a.y - 8), anchor="end")


n = nodes_from([
    ("pass", 0, 0, "A loop pass ran its tools\nand goal.is_met() is True", "term", "term", 330),
    ("evidence", 0, 1, "Collect the evidence\ngit diff broken -- checkout/  +  INTENT.md", "box", "new", 360),
    ("checker", 0, 2, "Checker (Haiku):\nallowed by INTENT.md?", "diamond", "new", 280),
    ("done", 1, 2, "PASS → DONE\nchange accepted", "term", "done", 220),
    ("down", -1, 2, "Checker unavailable\n→ NOT accepted\n(fail closed)", "term", "bad", 200),
    ("reject", 0, 3, "FAIL → violations back to the actor\neach quotes the rule it breaks", "box", "new", 360),
    ("next", 0, 4, "Next pass: the actor fixes again\n↻ goal check → checker again", "term", "model", 330),
])
e = [
    edge([n["pass"].bottom(), n["evidence"].top()]),
    edge([n["evidence"].bottom(), n["checker"].top()]),
    right_to(n["checker"], n["done"], "pass"),
    left_to(n["checker"], n["down"], "error"),
    yes_no_down(n["checker"], n["reject"], "fail"),
    edge([n["reject"].bottom(), n["next"].top()]),
]
res = ["Result: 3 diffs that all pass the 14 tests (1 honest fix, 2 cheats) × 2 rulebooks.",
       "Empty INTENT.md: all 3 PASS, cheats included (noticed, but no written rule to fail them on).",
       "Rules v1: both cheats FAIL, but the honest fix FAILS too: \"never relax validation\" was too vague.",
       "Rules v2 (+ \"min spend is inclusive\"): honest PASS, both cheats FAIL; one review misread a line.",
       "Lesson: a checker only enforces written intent, as precisely as it's written, and is still just an agent."]
render(f"{OUT}/stage5_flow.svg", "Stage 5: the checker, a second model reviews the work",
       "Tests decide whether the code works; the checker decides whether the change is allowed.",
       n, e, "new in this stage", res, height_for(5, len(res)))
print("stage5 ok")
