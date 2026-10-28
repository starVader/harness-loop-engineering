"""Run one phase of the stage 8 experiment, or summarise all of them.

    venv/bin/python stage8/run.py before      # held-out 04-06, nothing learned yet
    venv/bin/python stage8/run.py train       # 01-03: the runs the reflector learns from
    venv/bin/python stage8/run.py after       # held-out again, with the learned INTENT.md / LESSONS.md
    venv/bin/python stage8/run.py retrain     # 01-03 again: the overfitting check
    venv/bin/python stage8/run.py summary     # incidents per bug set per phase -> runs/stage8/summary.md

Each run: put checkout/ into the bug set, run the loop (Haiku actor, checker
on, gate off), then save the transcript, progress.json, the accepted diff and
the audit report as runs/stage8/<phase>-<NN>.*

The gate is off for these runs on purpose: a human explaining every fix would
catch the bugs themselves, and the experiment would measure the human, not
what the harness learned. The human gate guards what gets learned instead
(reflect.py gate).
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs" / "stage8"
INTENT_PATH = REPO_ROOT / "INTENT.md"
LESSONS_PATH = REPO_ROOT / "LESSONS.md"
INTENT_BEFORE = RUNS_DIR / "intent_before.md"
PYTHON = sys.executable

TRAIN = ["01", "02", "03"]
HELD_OUT = ["04", "05", "06"]
PHASES = {"before": HELD_OUT, "train": TRAIN, "after": HELD_OUT, "retrain": TRAIN}
LEARNING_PHASES = ("after", "retrain")  # run with what the outer loop learned
LOOP_ARGS = ["--fresh", "--actor-model", "haiku", "--no-gate"]


def short_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8] if path.exists() else "none"


def check_phase(phase: str) -> None:
    """Refuse a phase whose inputs would make the comparison meaningless."""
    learned = LESSONS_PATH.exists() or (INTENT_BEFORE.exists() and short_hash(INTENT_BEFORE) != short_hash(INTENT_PATH))
    if phase not in LEARNING_PHASES and learned:
        sys.exit(f"{phase}: INTENT.md or LESSONS.md has already changed since intent_before.md; "
                 f"'{phase}' must run before anything is learned")
    if phase in LEARNING_PHASES and not learned:
        print(f"warning: {phase} with nothing learned (INTENT.md unchanged, no LESSONS.md); this repeats 'before'")
    if not INTENT_BEFORE.exists():
        shutil.copy(INTENT_PATH, INTENT_BEFORE)
        print(f"froze the starting intent: {INTENT_BEFORE.relative_to(REPO_ROOT)}")


def run_one(phase: str, bugset: str) -> None:
    stem = RUNS_DIR / f"{phase}-{bugset}"
    tag = f"bugset-{bugset}"
    subprocess.run([PYTHON, "stage8/bugset.py", bugset], cwd=REPO_ROOT, check=True)
    header = (f"# stage 8 {phase} bug set {bugset}: INTENT.md {short_hash(INTENT_PATH)}, "
              f"LESSONS.md {short_hash(LESSONS_PATH)}\n")
    env = {**os.environ, "LOOP_BASELINE": tag}
    with stem.with_suffix(".md").open("w") as transcript:
        transcript.write(header)
        print(header, end="")
        loop = subprocess.Popen([PYTHON, "-u", "loop.py", *LOOP_ARGS], cwd=REPO_ROOT, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in loop.stdout:
            print(line, end="")
            transcript.write(line)
        loop.wait()
    shutil.copy(REPO_ROOT / "progress.json", stem.with_suffix(".progress.json"))
    diff = subprocess.run(["git", "diff", tag, "--", "checkout/"], cwd=REPO_ROOT,
                          capture_output=True, text=True, check=True).stdout
    stem.with_suffix(".diff").write_text(diff)
    audit = subprocess.run([PYTHON, "stage8/audit.py"], cwd=REPO_ROOT, capture_output=True, text=True).stdout
    stem.with_suffix(".audit").write_text(audit)
    print(audit)


def outcome(transcript: str) -> str:
    for marker, label in (("DONE:", "accepted"), ("CAP HIT", "cap hit"), ("STOPPED EARLY", "stopped"),
                          ("REVIEW UNAVAILABLE", "unavailable")):
        if marker in transcript:
            return label
    return "unfinished"


def summary() -> None:
    rows = ["| Phase | Bug set | Outcome | Passes | Checker rejections | Tokens in / out | Incidents |",
            "|---|---|---|---|---|---|---|"]
    totals = {}
    for phase, bugsets in PHASES.items():
        for bugset in bugsets:
            stem = RUNS_DIR / f"{phase}-{bugset}"
            if not stem.with_suffix(".md").exists():
                continue
            transcript = stem.with_suffix(".md").read_text()
            audit = stem.with_suffix(".audit").read_text() if stem.with_suffix(".audit").exists() else ""
            passes = len(re.findall(r"^--- pass \d+", transcript, flags=re.MULTILINE))
            tokens = re.search(r"total tokens: input=(\d+) output=(\d+)", transcript)
            incidents = re.findall(r"incident  (.+)", audit)
            totals[phase] = totals.get(phase, 0) + len(incidents)
            rows.append(f"| {phase} | {bugset} | {outcome(transcript)} | {passes} | "
                        f"{transcript.count('CHECKER REJECTED')} | "
                        f"{tokens.group(1) + ' / ' + tokens.group(2) if tokens else '?'} | "
                        f"{len(incidents)}: {'; '.join(incidents) or 'clean'} |")
    rows += ["", "| Phase | Total incidents |", "|---|---|"]
    rows += [f"| {phase} | {count} |" for phase, count in totals.items()]
    text = "\n".join(rows) + "\n"
    (RUNS_DIR / "summary.md").write_text(text)
    print(text)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in (*PHASES, "summary"):
        sys.exit(f"usage: stage8/run.py {{{'|'.join(PHASES)}|summary}} [NN ...]")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    phase = sys.argv[1]
    if phase == "summary":
        summary()
    else:
        check_phase(phase)
        for bugset in sys.argv[2:] or PHASES[phase]:
            run_one(phase, bugset.zfill(2))
        subprocess.run(["git", "restore", "--source=broken", "--", "checkout/"], cwd=REPO_ROOT, check=True)
        print(f"checkout/ restored to broken. Next: {'reflect.py propose' if phase == 'train' else 'stage8/run.py summary'}")
