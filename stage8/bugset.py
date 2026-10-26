"""Put checkout/ into one of the stage 8 bug sets.

    venv/bin/python stage8/bugset.py 03

Builds a tag `bugset-03` (green code + bugsets/bugset03.patch) the first time,
then restores checkout/ from it. Like `broken`, the tag is the baseline the
checker diffs against: run the loop with LOOP_BASELINE=bugset-03.

The tag's commit sits off to the side: main, the index and every file outside
checkout/ are left alone.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUGSETS_DIR = Path(__file__).resolve().parent / "bugsets"
GREEN_REF = "broken~1"  # the commit before the 4 stage 0 bugs went in


def git(*args: str, env: dict = None) -> str:
    completed = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, env=env)
    if completed.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{completed.stderr}")
    return completed.stdout.strip()


def ensure_tag(name: str) -> str:
    tag = f"bugset-{name}"
    exists = subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
                            cwd=REPO_ROOT, capture_output=True).returncode == 0
    if exists:
        return tag
    patch = BUGSETS_DIR / f"bugset{name}.patch"
    if not patch.exists():
        sys.exit(f"no such bug set: {patch.name}")
    with tempfile.TemporaryDirectory() as scratch:
        # A throwaway index, so the real one never sees the bug set
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
        git("read-tree", GREEN_REF, env=env)
        git("apply", "--cached", str(patch), env=env)
        tree = git("write-tree", env=env)
    commit = git("commit-tree", tree, "-p", GREEN_REF, "-m", f"stage 8 bug set {name}")
    git("tag", tag, commit)
    return tag


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: stage8/bugset.py NN   (01-06)")
    tag = ensure_tag(sys.argv[1].zfill(2))
    git("restore", f"--source={tag}", "--", "checkout/")
    print(f"checkout/ is now {tag}. Run the loop with LOOP_BASELINE={tag}")
