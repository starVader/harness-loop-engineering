"""The spine: what the loop remembers when the conversation is gone.

A crash loses the whole API conversation. The spine keeps what was *learned*
(which tests fail, which files were written, which tools ran), not what was
*read*: the model can always re-read a file, but it can't recover a decision.

Saved to progress.json after every pass (gitignored, and invisible to the
actor). Plain dataclasses + json: no dependency beyond the stdlib.
"""

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent
SPINE_PATH = REPO_ROOT / "progress.json"
CODE_DIR = REPO_ROOT / "checkout"

STATUS_RUNNING = "running"  # in progress, or crashed: safe to resume
STATUS_DONE = "done"  # goal verified: rerunning is a no-op
STATUS_STOPPED = "stopped"  # model stopped, cap hit, or accepted on its word


@dataclass
class PassRecord:
    pass_number: int
    tool_calls: List[str]  # e.g. "read_file(checkout/tax.py)"
    files_written: List[str]
    failing_tests: List[str]  # pytest node ids still failing after this pass
    tests_summary: str
    input_tokens: int
    output_tokens: int


@dataclass
class Spine:
    goal: str
    status: str
    code_fingerprint: str
    started_at: str
    passes: List[PassRecord] = field(default_factory=list)


def fingerprint_code() -> str:
    """Hash of every checkout/*.py file: changes whenever the code changes."""
    digest = hashlib.sha256()
    for path in sorted(CODE_DIR.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def new_spine(goal: str) -> Spine:
    return Spine(
        goal=goal,
        status=STATUS_RUNNING,
        code_fingerprint=fingerprint_code(),
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def load_spine() -> Optional[Spine]:
    """Read progress.json. A missing or unreadable file means no spine, never a crash."""
    if not SPINE_PATH.exists():
        return None
    try:
        raw = json.loads(SPINE_PATH.read_text())
        passes = [PassRecord(**record) for record in raw.pop("passes")]
        return Spine(passes=passes, **raw)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"spine: {SPINE_PATH.name} is unreadable ({exc}); ignoring it")
        return None


def save_spine(spine: Spine) -> None:
    """Atomic write: a crash mid-save leaves the previous spine intact."""
    spine.code_fingerprint = fingerprint_code()
    tmp_path = SPINE_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(asdict(spine), indent=2))
    os.replace(tmp_path, SPINE_PATH)


def failing_tests_from(pytest_output: str) -> List[str]:
    """Pull 'FAILED tests/x.py::name - ...' lines out of pytest's summary."""
    return [
        line.split()[1]
        for line in pytest_output.splitlines()
        if line.startswith("FAILED ")
    ]


def progress_note(spine: Spine) -> str:
    """The resume briefing the model reads in place of its lost conversation."""
    lines = [
        "This run is resuming after an interruption. Progress so far (from progress.json):",
    ]
    for record in spine.passes:
        lines.append(f"- pass {record.pass_number}: {', '.join(record.tool_calls) or 'no tools'} -> {record.tests_summary}")
    written = sorted({path for record in spine.passes for path in record.files_written})
    lines.append(f"Files changed so far: {', '.join(written) or 'none'}.")
    latest = spine.passes[-1] if spine.passes else None
    if latest and latest.failing_tests:
        lines.append("Still failing: " + ", ".join(latest.failing_tests) + ".")
    lines.append("Continue from here; you do not need to repeat work that is already recorded.")
    return "\n".join(lines)
