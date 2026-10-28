"""Scenarios: the starting states the loop is asked to repair.

    python -m harness.scenario list
    python -m harness.scenario apply broken      # the 4 bugs of stages 1-7
    python -m harness.scenario apply bugset04    # one of the stage 8 bug sets
    python -m harness.scenario apply green       # back to the committed, working code
    python -m harness.scenario status
    python -m harness.scenario diff              # what the loop changed since the scenario was applied

checkout/ is committed green. A scenario is a patch on top of it. Applying
one restores checkout/ from git, applies the patch, and snapshots the result
in .harness/baseline/: that snapshot is what "the loop's change" is measured
against, by the checker, the gate and the experiment. No tags, no history:
a fresh clone can apply any scenario.

Applying discards whatever is in checkout/. If checkout/ has changes and no
scenario was ever applied, they're yours, not the loop's, and apply refuses
unless you pass --force.
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from harness.paths import CODE_DIR, REPO_ROOT, SCENARIOS_DIR, STATE_DIR

BASELINE_DIR = STATE_DIR / "baseline"
CURRENT_FILE = STATE_DIR / "scenario"


class NoScenario(Exception):
    """No scenario has been applied, so there is no baseline to diff against."""


class UnsavedChanges(Exception):
    """checkout/ has edits that no scenario made; applying would throw them away."""


def scenarios() -> Dict[str, Path]:
    """name -> patch. 'green' has no patch."""
    found = {"broken": SCENARIOS_DIR / "broken.patch"}
    for patch in sorted((SCENARIOS_DIR / "bugsets").glob("bugset*.patch")):
        found[patch.stem] = patch
    return found


def _git(*args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout


def apply(name: str, force: bool = False) -> None:
    """Put checkout/ into the named scenario and make it the baseline."""
    known = scenarios()
    if name != "green" and name not in known:
        raise ValueError(f"unknown scenario {name!r}; one of: green, {', '.join(known)}")
    if not force and not CURRENT_FILE.exists() and _git("status", "--porcelain", "--", "checkout/").strip():
        raise UnsavedChanges("checkout/ has changes no scenario made (commit or stash them, or pass --force)")
    _git("restore", "--source=HEAD", "--", "checkout/")
    if name != "green":
        _git("apply", str(known[name]))
    if BASELINE_DIR.exists():
        shutil.rmtree(BASELINE_DIR)
    BASELINE_DIR.mkdir(parents=True)
    for path in CODE_DIR.glob("*.py"):
        shutil.copy(path, BASELINE_DIR / path.name)
    CURRENT_FILE.write_text(name + "\n")


def current() -> str:
    if not CURRENT_FILE.exists():
        raise NoScenario("no scenario applied yet: run `python -m harness.scenario apply broken`")
    return CURRENT_FILE.read_text().strip()


def current_diff() -> str:
    """What the loop changed: checkout/*.py against the scenario's starting snapshot, as a git-style patch."""
    current()
    names = sorted({path.name for path in CODE_DIR.glob("*.py")} | {path.name for path in BASELINE_DIR.glob("*.py")})
    parts: List[str] = []
    for name in names:
        before, after = BASELINE_DIR / name, CODE_DIR / name
        completed = subprocess.run(
            ["git", "diff", "--no-index", "--",
             str(before) if before.exists() else "/dev/null", str(after) if after.exists() else "/dev/null"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if completed.stdout:
            parts.append(_relabel(completed.stdout, name))
    return "".join(parts)


def _relabel(patch: str, name: str) -> str:
    """git diff --no-index names the snapshot's real path; call both sides checkout/<name>, like a normal diff."""
    lines = []
    for line in patch.splitlines(keepends=True):
        if line.startswith("diff --git "):
            line = f"diff --git a/checkout/{name} b/checkout/{name}\n"
        elif line.startswith("--- ") and not line.startswith("--- /dev/null"):
            line = f"--- a/checkout/{name}\n"
        elif line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
            line = f"+++ b/checkout/{name}\n"
        lines.append(line)
    return "".join(lines)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "list":
        print("green  (the committed, working code)")
        for scenario_name, patch in scenarios().items():
            print(f"{scenario_name:<7} {patch.relative_to(REPO_ROOT)}")
    elif command == "apply" and len(sys.argv) in (3, 4) and sys.argv[3:] in ([], ["--force"]):
        try:
            apply(sys.argv[2], force=sys.argv[3:] == ["--force"])
        except (UnsavedChanges, ValueError) as exc:
            sys.exit(str(exc))
        print(f"checkout/ is now scenario {sys.argv[2]!r}; the loop's changes are measured from here")
    elif command == "diff":
        print(current_diff(), end="")
    elif command == "status":
        try:
            print(f"scenario: {current()}")
            diff = current_diff()
            print(f"changed since applied: {'yes' if diff else 'no'}")
        except NoScenario as exc:
            print(exc)
    else:
        sys.exit("usage: python -m harness.scenario {list | apply NAME [--force] | status | diff}")
