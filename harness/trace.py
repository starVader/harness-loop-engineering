"""The trace: one JSON line for everything that happened in a run.

The transcript is for people; the spine is for resuming. The trace is for
asking questions afterwards: which call cost the most, which check rejected
what, how long the human took. Every model call, tool call, verdict, gate
decision, compaction, budget breach and escalation is one event, tied to one
run_id, written and flushed as it happens, so a crash keeps everything up to
the crash.

    python -m harness.trace list
    python -m harness.trace show latest        # or a run id
"""

import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from harness.paths import STATE_DIR

TRACES_DIR = STATE_DIR / "traces"


def new_run_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(3)}"


class Trace:
    def __init__(self, run_id: Optional[str] = None) -> None:
        self.run_id = run_id or new_run_id()
        self.path = TRACES_DIR / f"{self.run_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, kind: str, pass_number: Optional[int] = None, **fields) -> None:
        record = {"run_id": self.run_id, "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                  "pass": pass_number, "event": kind, **fields}
        with self.path.open("a") as out:
            out.write(json.dumps(record, default=str) + "\n")


def run_ids() -> List[str]:
    return [path.stem for path in sorted(TRACES_DIR.glob("*.jsonl"))]


def load(run_id: str = "latest", directory: Optional[Path] = None) -> List[Dict]:
    directory = directory or TRACES_DIR
    if run_id == "latest":
        found = sorted(directory.glob("*.jsonl"), key=lambda path: path.stat().st_mtime)
        if not found:
            raise FileNotFoundError(f"no traces in {directory}")
        path = found[-1]
    else:
        path = directory / f"{run_id}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def totals(events: List[Dict]) -> Dict:
    """Tokens and cost across every model call in the run: the actor's and the checker's."""
    calls = [event for event in events if event["event"] in ("model_call", "checker_verdict")]
    return {
        "input_tokens": sum(event.get("input_tokens", 0) for event in calls),
        "output_tokens": sum(event.get("output_tokens", 0) for event in calls),
        "cost_usd": round(sum(event.get("cost_usd", 0.0) for event in calls), 6),
    }


def show(events: List[Dict]) -> str:
    start = next((event for event in events if event["event"] == "run_start"), {})
    lines = [f"run {start.get('run_id', '?')}  scenario={start.get('scenario')}  actor={start.get('actor_model')}  "
             f"sandbox={start.get('sandbox')}",
             "pass | tools                          | tests                 | sensors | checker | gate | in / out      | cost"]
    by_pass: Dict[int, List[Dict]] = {}
    for event in events:
        if event.get("pass") is not None:
            by_pass.setdefault(event["pass"], []).append(event)
    for number, group in sorted(by_pass.items()):
        def last(kind: str, field: str) -> str:
            found = [event.get(field) for event in group if event["event"] == kind]
            return str(found[-1]) if found else "-"
        tools = ",".join(event["name"] for event in group if event["event"] == "tool_call") or "-"
        calls = [event for event in group if event["event"] in ("model_call", "checker_verdict")]
        tokens = f"{sum(e.get('input_tokens', 0) for e in calls)} / {sum(e.get('output_tokens', 0) for e in calls)}"
        cost = sum(e.get("cost_usd", 0.0) for e in calls)
        lines.append(f"{number:>4} | {tools[:30]:<30} | {last('goal_check', 'tests')[:21]:<21} | "
                     f"{last('sensor_verdict', 'verdict'):<7} | {last('checker_verdict', 'verdict'):<7} | "
                     f"{last('gate_decision', 'verdict'):<4} | {tokens:<13} | ${cost:.4f}")
    for event in events:
        if event["event"] in ("compaction", "budget_exceeded", "escalation"):
            lines.append(f"  {event['event']} after pass {event.get('pass')}: {event.get('reason', '')}".rstrip())
    end = next((event for event in events if event["event"] == "run_end"), None)
    total = totals(events)
    lines.append(f"end: {end['status'] if end else 'no run_end (crashed or still running)'}  "
                 f"tokens {total['input_tokens']} / {total['output_tokens']}  cost ${total['cost_usd']:.4f}")
    return "\n".join(lines)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "show"
    if command == "list":
        print("\n".join(run_ids()) or "no traces yet")
    elif command == "show":
        print(show(load(sys.argv[2] if len(sys.argv) > 2 else "latest")))
    else:
        sys.exit("usage: python -m harness.trace {list | show [run_id|latest]}")
