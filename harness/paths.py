"""Where everything lives. One place, so the self-tests can point the harness at a copy of the repo.

HARNESS_ROOT  run against another checkout of this repo (the self-tests use a temp copy)
HARNESS_INTENT  the intent file the actor and checker read instead of INTENT.md (stage 6, stage 8)
"""

import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get("HARNESS_ROOT", Path(__file__).resolve().parent.parent)).resolve()
CODE_DIR = REPO_ROOT / "checkout"  # the system under repair; committed green
TESTS_DIR = REPO_ROOT / "tests"  # the visible oracle
SCENARIOS_DIR = REPO_ROOT / "scenarios"  # bug patches, cheats, intents, the audit: never visible to the actor
STATE_DIR = REPO_ROOT / ".harness"  # run state: the spine, the scenario baseline, gate explanations
RUNS_DIR = REPO_ROOT / "runs"  # raw output of experiments, gitignored
STAGE8_DIR = RUNS_DIR / "stage8"  # the stage 8 experiment: runs, proposals, decisions, summary
LEARNED_DIR = STAGE8_DIR / "learned"  # what the outer loop learned, never the committed files
LEARNED_INTENT = LEARNED_DIR / "INTENT.md"  # starts as a copy of the committed INTENT.md
LEARNED_LESSONS = LEARNED_DIR / "LESSONS.md"
DEFAULT_INTENT = REPO_ROOT / "INTENT.md"


def intent_path() -> Path:
    """The intent in force for this run. Read at call time, so a flag set in main() reaches every module."""
    override = os.environ.get("HARNESS_INTENT")
    return Path(override).resolve() if override else DEFAULT_INTENT
