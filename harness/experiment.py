"""Stage 8's experiment: does the outer loop learn something that transfers?

    python -m harness.experiment before     # held-out bug sets 04-06, nothing learned yet
    python -m harness.experiment train      # 01-03: the runs the reflector learns from
    python -m harness.reflect propose       # (the outer loop proposes rules and lessons)
    python -m harness.reflect gate          # (you accept or reject each one)
    python -m harness.experiment after      # held-out again, with what was learned
    python -m harness.experiment retrain    # 01-03 again: the overfitting check
    python -m harness.experiment summary    # incidents per bug set per phase -> runs/stage8/summary.md

Add --sandbox docker to any phase to run the actor's code (and the audit) in the container.

Each run applies a bug set, runs the loop (Haiku actor, checker on, gate off)
and saves runs/stage8/<phase>-<NN>.md/.diff/.audit/.progress.json/.trace.jsonl. `before`
and `train` use the committed INTENT.md and no lessons; `after` and `retrain`
use runs/stage8/learned/.

The gate is off for these runs on purpose: a human explaining every fix would
catch the bugs themselves, and the experiment would measure the human, not
what the harness learned. Here the human gate guards what gets *learned*
(reflect.py gate), not what gets merged. Delete runs/stage8/ to start over.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from typing import List, Optional

from harness.audit import broken_rules
from harness.paths import LEARNED_INTENT, LEARNED_LESSONS, REPO_ROOT, STAGE8_DIR, STATE_DIR
from harness.scenario import apply, current_diff
from harness.spine import load_spine
from harness.trace import TRACES_DIR, load as load_trace, totals

TRAIN = ["bugset01", "bugset02", "bugset03"]
HELD_OUT = ["bugset04", "bugset05", "bugset06"]
PHASES = {"before": HELD_OUT, "train": TRAIN, "after": HELD_OUT, "retrain": TRAIN}
LEARNING_PHASES = ("after", "retrain")
LOOP_ARGS = ["--fresh", "--actor-model", "haiku", "--no-gate"]


def loop_command(phase: str) -> List[str]:
    command = [sys.executable, "-u", "-m", "harness.loop", *LOOP_ARGS]
    if phase in LEARNING_PHASES:
        if LEARNED_INTENT.exists():
            command += ["--intent", str(LEARNED_INTENT)]
        if LEARNED_LESSONS.exists():
            command += ["--lessons", str(LEARNED_LESSONS)]
        if len(command) == 4 + len(LOOP_ARGS):
            print(f"warning: {phase} with nothing learned (no runs/stage8/learned/); this repeats 'before'")
    return command


def new_run_id(known: set) -> Optional[str]:
    """The run id this loop process added to the spine, or None if it never got that far."""
    spine = load_spine()
    if spine is None or not spine.run_ids or spine.run_ids[-1] in known:
        return None
    return spine.run_ids[-1]


def run_one(phase: str, bugset: str) -> None:
    stem = STAGE8_DIR / f"{phase}-{bugset}"
    for suffix in (".progress.json", ".trace.jsonl", ".diff", ".audit"):
        stem.with_suffix(suffix).unlink(missing_ok=True)  # never leave an older attempt's files under this name
    apply(bugset)
    previous = load_spine()
    known = set(previous.run_ids) if previous else set()
    command = loop_command(phase)
    header = f"# stage 8 {phase} {bugset}: {' '.join(command[3:])}\n"
    with stem.with_suffix(".md").open("w") as transcript:
        transcript.write(header)
        print(header, end="")
        loop = subprocess.Popen(command, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in loop.stdout:
            print(line, end="")
            transcript.write(line)
        loop.wait()
    run_id = new_run_id(known)
    if run_id is None:
        # The loop exited before starting (no sandbox, no scenario...): nothing of this run to save or audit
        stem.with_suffix(".audit").write_text("AUDIT: skipped, the loop did not start\n")
        print("AUDIT: skipped, the loop did not start")
        return
    shutil.copy(STATE_DIR / "progress.json", stem.with_suffix(".progress.json"))
    if (TRACES_DIR / f"{run_id}.jsonl").exists():
        shutil.copy(TRACES_DIR / f"{run_id}.jsonl", stem.with_suffix(".trace.jsonl"))
    stem.with_suffix(".diff").write_text(current_diff())
    incidents = broken_rules()
    report = "AUDIT: clean, no business rule broken\n" if not incidents else (
        f"AUDIT: {len(incidents)} incident(s)\n" + "".join(f"  incident  {rule.replace('_', ' ')}\n" for rule in incidents))
    stem.with_suffix(".audit").write_text(report)
    print(report)


def outcome(transcript: str) -> str:
    for marker, label in (("DONE:", "accepted"), ("ESCALATED (", "escalated"), ("STOPPED EARLY", "stopped"),
                          ("REVIEW UNAVAILABLE", "unavailable"), ("NOT STARTED", "not started")):
        if marker in transcript:
            return label
    return "unfinished"


def summary() -> str:
    rows = ["| Phase | Bug set | Outcome | Passes | Rejections (rules / checker) | Tokens in / out | Cost | Incidents |",
            "|---|---|---|---|---|---|---|---|"]
    incident_totals = {}
    for phase, bugsets in PHASES.items():
        for bugset in bugsets:
            stem = STAGE8_DIR / f"{phase}-{bugset}"
            if not stem.with_suffix(".md").exists():
                continue
            transcript = stem.with_suffix(".md").read_text()
            audit = stem.with_suffix(".audit").read_text() if stem.with_suffix(".audit").exists() else ""
            passes = len(re.findall(r"^--- pass \d+", transcript, flags=re.MULTILINE))
            tokens = re.search(r"total tokens: input=(\d+) output=(\d+)", transcript)
            trace_path = stem.with_suffix(".trace.jsonl")
            cost = f"${totals(load_trace(trace_path.stem, trace_path.parent))['cost_usd']:.4f}" if trace_path.exists() else "?"
            incidents = re.findall(r"incident  (.+)", audit)
            incident_totals[phase] = incident_totals.get(phase, 0) + len(incidents)
            rows.append(f"| {phase} | {bugset} | {outcome(transcript)} | {passes} | "
                        f"{transcript.count('FIXED RULE REJECTED')} / {transcript.count('CHECKER REJECTED')} | "
                        f"{tokens.group(1) + ' / ' + tokens.group(2) if tokens else '?'} | {cost} | "
                        f"{len(incidents)}: {'; '.join(incidents) or 'clean'} |")
    rows += ["", "| Phase | Total incidents |", "|---|---|"]
    rows += [f"| {phase} | {count} |" for phase, count in incident_totals.items()]
    text = "\n".join(rows) + "\n"
    (STAGE8_DIR / "summary.md").write_text(text)
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 8: learn on bug sets 01-03, measure on 04-06.")
    parser.add_argument("phase", choices=[*PHASES, "summary"])
    parser.add_argument("bugsets", nargs="*", help="only these bug sets (default: the phase's own)")
    parser.add_argument("--sandbox", choices=("local", "docker"), help="where actor-written code and the audit run")
    args = parser.parse_args()
    if args.sandbox:
        os.environ["HARNESS_SANDBOX"] = args.sandbox
    STAGE8_DIR.mkdir(parents=True, exist_ok=True)
    phase_name = args.phase
    if phase_name == "summary":
        print(summary())
    else:
        for name in args.bugsets or PHASES[phase_name]:
            run_one(phase_name, name)
        apply("broken")
        print("checkout/ is back to scenario 'broken'. Next: "
              + ("python -m harness.reflect propose" if phase_name == "train" else "python -m harness.experiment summary"))
