"""The human gate: no change is accepted until a human can explain it.

The tests decide whether the code works, the checker whether the change is
allowed. The gate decides whether anyone *understands* it. It shows the change
one hunk at a time and asks for a one-sentence explanation of each. A hunk
the human can't explain isn't accepted; "reject: <why>" sends it back to the
actor, the same way a checker failure does.

Explanations go to outputs/stage7/fixes.md, keyed by a hash of the hunk's
changed lines. Change the code afterwards and the old explanation no longer
matches: `gate.py --check` fails until someone explains the new hunk.

The gate is generic: anything that becomes a list of GateItems can be gated.
Stage 8 gates the reflector's proposals with it.
"""

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from checker import BASELINE_REF, current_diff

REPO_ROOT = Path(__file__).resolve().parent
FIXES_PATH = REPO_ROOT / "outputs" / "stage7" / "fixes.md"
MIN_WORDS = 6
REJECT_PREFIX = "reject:"


@dataclass(frozen=True)
class GateItem:
    id: str  # stable: survives line shifts, changes when the content changes
    title: str
    body: str


@dataclass(frozen=True)
class Decision:
    item_id: str
    title: str
    accepted: bool
    sentence: str  # the explanation, or the reason for rejecting


@dataclass(frozen=True)
class GateResult:
    decisions: List[Decision]

    @property
    def passed(self) -> bool:
        return all(decision.accepted for decision in self.decisions)

    @property
    def rejections(self) -> List[Decision]:
        return [decision for decision in self.decisions if not decision.accepted]


class GateUnavailable(Exception):
    """No human to ask (no terminal). The change must not be accepted."""


def hunks(diff: str) -> List[GateItem]:
    """One GateItem per change block, id'd by file and a hash of its +/- lines.

    Git merges nearby changes into one hunk; the gate splits them again, so
    each sentence explains one change, not two that happen to sit close.
    """
    items: List[GateItem] = []
    path = ""
    for line_group in _hunk_bodies(diff):
        if isinstance(line_group, str):
            path = line_group
            continue
        header, lines = line_group
        function = _function_name(header)
        index = 0
        while index < len(lines):
            line = lines[index]
            match = re.match(r"[ -]\s*def (\w+)", line)
            if match:
                function = match.group(1)
            if line[:1] not in "+-":
                index += 1
                continue
            end = index
            while end < len(lines) and lines[end][:1] in "+-":
                end += 1
            block = lines[max(0, index - CONTEXT_LINES):end + CONTEXT_LINES]
            changed = "\n".join(lines[index:end])
            digest = hashlib.sha256(f"{path}\n{changed}".encode()).hexdigest()[:8]
            title = f"{path} ({function})" if function else path
            items.append(GateItem(id=f"{path}#{digest}", title=title, body="\n".join(block)))
            index = end
    return items


CONTEXT_LINES = 2


def _function_name(hunk_header: str) -> str:
    match = re.search(r"@@.*@@.*?\bdef (\w+)", hunk_header)
    return match.group(1) if match else ""


def _hunk_bodies(diff: str):
    """Yields a file path when a new file starts, then (header, lines) per hunk."""
    header = None
    lines: List[str] = []
    for line in diff.splitlines():
        if line.startswith(("diff --git", "+++ ", "--- ", "@@")) and header is not None:
            yield header, lines
            header, lines = None, []
        if line.startswith("+++ "):
            yield line[4:].removeprefix("b/")
        elif line.startswith("@@"):
            header = line
        elif header is not None and not line.startswith("\\"):
            lines.append(line)
    if header is not None:
        yield header, lines


def problem_with(sentence: str) -> Optional[str]:
    """Why this isn't an acceptable explanation, or None if it is."""
    words = sentence.split()
    if len(words) < MIN_WORDS:
        return f"too short: say what changed and why, in at least {MIN_WORDS} words"
    if re.search(r"[.!?]\s+\S", sentence.strip()):
        return "one sentence, please: if it needs two, the change may be doing two things"
    return None


def ask_human(items: List[GateItem], read: Callable[[str], str] = input) -> GateResult:
    """Show each item and collect an explanation or a rejection. Raises GateUnavailable with no terminal."""
    if read is input and not sys.stdin.isatty():
        raise GateUnavailable("stdin is not a terminal")
    decisions: List[Decision] = []
    for number, item in enumerate(items, start=1):
        print(f"\n--- gate {number}/{len(items)}: {item.title}  [{item.id}]")
        print(item.body)
        while True:
            try:
                answer = read(f"Explain in one sentence, or '{REJECT_PREFIX} <why>': ").strip()
            except EOFError as exc:
                raise GateUnavailable("input closed before every item was decided") from exc
            if answer.lower().startswith(REJECT_PREFIX):
                reason = answer[len(REJECT_PREFIX):].strip()
                if reason:
                    decisions.append(Decision(item.id, item.title, accepted=False, sentence=reason))
                    break
                print("  a rejection needs a reason the actor can act on")
                continue
            problem = problem_with(answer)
            if problem is None:
                decisions.append(Decision(item.id, item.title, accepted=True, sentence=answer))
                break
            print(f"  {problem}")
    return GateResult(decisions)


def record(result: GateResult, path: Path = FIXES_PATH, baseline: str = BASELINE_REF) -> None:
    """Append this gate session to the fixes file: the human's words, kept with the code they explain."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} (baseline {baseline})"]
    for decision in result.decisions:
        verb = "accepted" if decision.accepted else "rejected"
        lines.append(f"- {verb} `{decision.item_id}` {decision.title}: {decision.sentence}")
    with path.open("a") as fixes:
        fixes.write("\n".join(lines) + "\n")


def recorded_explanations(path: Path = FIXES_PATH) -> Dict[str, str]:
    """item id -> the latest accepted explanation in the fixes file."""
    if not path.exists():
        return {}
    explained: Dict[str, str] = {}
    for match in re.finditer(r"^- accepted `([^`]+)` .*?: (.+)$", path.read_text(), flags=re.MULTILINE):
        explained[match.group(1)] = match.group(2)
    return explained


def unexplained(items: List[GateItem], path: Path = FIXES_PATH) -> List[GateItem]:
    """The items nobody has explained yet: new hunks, or hunks that changed since they were explained."""
    explained = recorded_explanations(path)
    return [item for item in items if item.id not in explained]


def feedback_for_actor(result: GateResult) -> str:
    """The message the actor gets when the human rejects part of its change."""
    lines = ["Your change passes the tests and the checker, but the human reviewer rejected part of it:"]
    for decision in result.rejections:
        lines.append(f"- {decision.title}: {decision.sentence}")
    lines.append("Rework those parts. Keep the tests passing and keep to INTENT.md.")
    return "\n".join(lines)


def print_result(result: GateResult) -> None:
    accepted = len(result.decisions) - len(result.rejections)
    print(f"gate: {'PASS' if result.passed else 'FAIL'} ({accepted}/{len(result.decisions)} explained)")
    for decision in result.rejections:
        print(f"  rejected   {decision.title}: {decision.sentence}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gate the current change on a human's explanations.")
    parser.add_argument("--check", action="store_true",
                        help="don't ask; exit 1 if any hunk lacks a recorded explanation")
    parser.add_argument("--diff", type=Path, help=f"a patch file (default: git diff {BASELINE_REF} -- checkout/)")
    parser.add_argument("--fixes", type=Path, default=FIXES_PATH, help="where explanations are kept")
    args = parser.parse_args()
    items = hunks(args.diff.read_text() if args.diff else current_diff())
    if args.check:
        missing = unexplained(items, args.fixes)
        for item in missing:
            print(f"unexplained  {item.title}  [{item.id}]")
        print(f"gate check: {len(items) - len(missing)}/{len(items)} hunks explained")
        sys.exit(1 if missing else 0)
    pending = unexplained(items, args.fixes)
    print(f"=== gate: {len(items)} hunk(s), {len(items) - len(pending)} already explained")
    if pending:
        try:
            gate_result = ask_human(pending)
        except GateUnavailable as exc:
            sys.exit(f"GATE UNAVAILABLE: {exc}; not accepting the change")
        record(gate_result, args.fixes)
        print_result(gate_result)
        sys.exit(0 if gate_result.passed else 1)
