"""The spine: what the loop remembers when the conversation is gone.

A crash loses the whole API conversation. The spine keeps what was *learned*
(which tests fail, which files were written, which tools ran), not what was
*read*: the model can always re-read a file, but it can't recover a decision.

Saved to .harness/progress.json after every pass (gitignored, and invisible
to the actor). Plain dataclasses + json: no dependency beyond the stdlib.
"""

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from harness.paths import CODE_DIR, STATE_DIR

SPINE_PATH = STATE_DIR / "progress.json"

STATUS_RUNNING = "running"  # in progress, or crashed: safe to resume
STATUS_DONE = "done"  # goal verified: rerunning is a no-op
STATUS_STOPPED = "stopped"  # model stopped early, a reviewer was unavailable, or accepted on its word
STATUS_ESCALATED = "escalated"  # a budget ran out: a human has to look before anything continues


@dataclass
class PassRecord:
    pass_number: int
    tool_calls: List[str]  # e.g. "read_file(checkout/tax.py)"
    files_written: List[str]
    failing_tests: List[str]  # pytest node ids still failing after this pass
    tests_summary: str
    input_tokens: int
    output_tokens: int
    compacted: bool = False  # the conversation was restarted from the spine after this pass
    sensors: Optional[str] = None  # "pass" / "fail" when the fixed rules checked this pass
    checker: Optional[str] = None  # "pass" / "fail" when the checker reviewed this pass
    gate: Optional[str] = None  # "pass" / "fail" when a human reviewed this pass


@dataclass
class Spine:
    goal: str
    status: str
    code_fingerprint: str
    started_at: str
    passes: List[PassRecord] = field(default_factory=list)
    run_ids: List[str] = field(default_factory=list)  # one per process that worked on this spine: see harness/trace.py
    escalation_reason: Optional[str] = None
    spent_usd: float = 0.0  # actor + checker, across every run of this spine, so a resume can't reset the budget


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
    SPINE_PATH.parent.mkdir(parents=True, exist_ok=True)
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


def progress_note(spine: Spine, reason: str) -> str:
    """The briefing the model reads in place of its lost conversation.

    reason says why the conversation restarted, e.g. "after an interruption"
    or "to keep the context small", so the model is told the truth about it.
    """
    lines = [
        f"This conversation was restarted {reason}. Progress so far (from progress.json):",
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
