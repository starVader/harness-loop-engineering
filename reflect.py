"""The outer loop: read past runs, propose what to write down next.

    venv/bin/python reflect.py propose   # one model call -> runs/stage8/proposals.{json,md}
    venv/bin/python reflect.py gate      # you accept or reject each one; accepted ones are applied

The inner loop fixes code. This loop fixes the *harness*: the rules in
INTENT.md that the actor and checker read, and LESSONS.md, which the actor
gets in its system prompt. It learns only from training runs: their
transcripts, diffs, and the audit's incident names. It never sees the audit's
tests, the bug sets, or a held-out run, and it never applies anything itself:
every proposal goes through the human gate.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import List

import anthropic

from gate import GateItem, GateUnavailable, ask_human, print_result, record

REPO_ROOT = Path(__file__).resolve().parent
RUNS_DIR = REPO_ROOT / "runs" / "stage8"
INTENT_PATH = REPO_ROOT / "INTENT.md"
LESSONS_PATH = REPO_ROOT / "LESSONS.md"
PROPOSALS_JSON = RUNS_DIR / "proposals.json"
PROPOSALS_MD = RUNS_DIR / "proposals.md"
DECISIONS_PATH = RUNS_DIR / "decisions.md"
TRAIN_PREFIX = "train-"  # the only runs the reflector may read
REFLECT_MODEL = "claude-opus-5-5"
REFLECT_MAX_TOKENS = 16000

REFLECT_SYSTEM_PROMPT = """
You improve the harness around a coding agent that fixes bugs in a checkout
service for an Indian store (GST invoices, discount codes, money in rupees and
paise). You are given the agent's past runs: what it did, the code it got
accepted, and the incidents a later audit found in that accepted code. The
visible tests passed in every run, so each incident is a business rule the
tests don't check and nobody wrote down.

Propose a small number of changes, each one of:
- intent_rule: a business rule for INTENT.md. Both the agent and a reviewer
  read INTENT.md. Write it in business words an accountant would understand.
  Never name a file, function, variable, line or bug: the next bug will be
  somewhere else, and a rule only helps if it still applies there.
- lesson: advice for the agent on how to work, which goes in its system
  prompt (for example, what to check before calling a fix done).

Every proposal must be backed by evidence in the runs: cite the run and the
incident or behaviour. Don't restate a rule INTENT.md already has. Don't
propose changing tests, tools, or how success is measured. Prefer three good
proposals to ten weak ones. Say why each one would also help on bugs you
haven't seen.
"""

PROPOSALS_SCHEMA = {
    "type": "object",
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["intent_rule", "lesson"]},
                    "text": {"type": "string"},
                    "evidence": {"type": "string"},
                    "why_it_generalises": {"type": "string"},
                },
                "required": ["kind", "text", "evidence", "why_it_generalises"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["proposals", "summary"],
    "additionalProperties": False,
}


def training_evidence() -> str:
    """Every training run's transcript, accepted diff and audit report, in one block per run."""
    runs = sorted(path.stem for path in RUNS_DIR.glob(f"{TRAIN_PREFIX}*.md"))
    if not runs:
        sys.exit(f"no training runs in {RUNS_DIR}; run `stage8/run.py train` first")
    blocks = []
    for run in runs:
        parts = [f'<run name="{run}">']
        for suffix, tag in ((".md", "transcript"), (".diff", "accepted_diff"), (".audit", "audit")):
            path = RUNS_DIR / f"{run}{suffix}"
            if path.exists():
                parts.append(f"<{tag}>\n{path.read_text()}\n</{tag}>")
        parts.append("</run>")
        blocks.append("\n".join(parts))
    print(f"reflect: reading {len(runs)} training run(s): {', '.join(runs)}")
    return "\n\n".join(blocks)


def propose() -> None:
    lessons = LESSONS_PATH.read_text() if LESSONS_PATH.exists() else "(none yet)"
    content = (
        f"<intent_md>\n{INTENT_PATH.read_text()}\n</intent_md>\n\n"
        f"<lessons_md>\n{lessons}\n</lessons_md>\n\n"
        f"{training_evidence()}"
    )
    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=REFLECT_MODEL,
        max_tokens=REFLECT_MAX_TOKENS,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # a safety decline is retried on another model inside the same call
        system=REFLECT_SYSTEM_PROMPT,
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": PROPOSALS_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    )
    if response.stop_reason != "end_turn":
        sys.exit(f"reflect: stopped with stop_reason={response.stop_reason}; no proposals written")
    text = next((block.text for block in response.content if block.type == "text"), None)
    if text is None:
        sys.exit("reflect: the model returned no text block")
    raw = json.loads(text)
    PROPOSALS_JSON.write_text(json.dumps(raw, indent=2))
    PROPOSALS_MD.write_text(proposals_markdown(raw))
    print(f"reflect: {len(raw['proposals'])} proposal(s) -> {PROPOSALS_MD.relative_to(REPO_ROOT)} "
          f"(tokens in={response.usage.input_tokens} out={response.usage.output_tokens})")
    print(f"  summary  {raw['summary']}")
    print("Next: venv/bin/python reflect.py gate")


def proposals_markdown(raw: dict) -> str:
    lines = ["# Proposals from the outer loop", "", raw["summary"], ""]
    for number, proposal in enumerate(raw["proposals"], start=1):
        lines += [
            f"## {number}. {proposal['kind']}",
            f"> {proposal['text']}",
            "",
            f"- **Evidence:** {proposal['evidence']}",
            f"- **Why it generalises:** {proposal['why_it_generalises']}",
            "",
        ]
    return "\n".join(lines)


def gate_items(raw: dict) -> List[GateItem]:
    items = []
    for proposal in raw["proposals"]:
        digest = hashlib.sha256(proposal["text"].encode()).hexdigest()[:8]
        body = (f"  {proposal['text']}\n\n  evidence: {proposal['evidence']}\n"
                f"  why it generalises: {proposal['why_it_generalises']}")
        items.append(GateItem(id=f"{proposal['kind']}#{digest}", title=proposal["kind"], body=body))
    return items


def apply_accepted(raw: dict, accepted_ids: List[str]) -> None:
    """Append accepted rules to INTENT.md's Rules section (the last one) and lessons to LESSONS.md."""
    by_id = {item.id: proposal for item, proposal in zip(gate_items(raw), raw["proposals"])}
    rules = [by_id[item_id]["text"] for item_id in accepted_ids if item_id.startswith("intent_rule#")]
    lessons = [by_id[item_id]["text"] for item_id in accepted_ids if item_id.startswith("lesson#")]
    if rules:
        intent = INTENT_PATH.read_text().rstrip("\n")
        INTENT_PATH.write_text(intent + "\n" + "\n".join(f"- {rule}" for rule in rules) + "\n")
        print(f"applied: {len(rules)} rule(s) added to INTENT.md")
    if lessons:
        existing = LESSONS_PATH.read_text().rstrip("\n") if LESSONS_PATH.exists() else "# Lessons from past runs"
        LESSONS_PATH.write_text(existing + "\n" + "\n".join(f"- {lesson}" for lesson in lessons) + "\n")
        print(f"applied: {len(lessons)} lesson(s) added to LESSONS.md")


def gate() -> None:
    if not PROPOSALS_JSON.exists():
        sys.exit("no proposals yet; run `reflect.py propose` first")
    raw = json.loads(PROPOSALS_JSON.read_text())
    print("For each proposal: one sentence on why you accept it, or 'reject: <why>'.")
    print("Reject anything that names code, or that only fixes the bugs it saw.")
    try:
        result = ask_human(gate_items(raw))
    except GateUnavailable as exc:
        sys.exit(f"GATE UNAVAILABLE: {exc}; nothing applied")
    record(result, DECISIONS_PATH, baseline="training runs")
    print_result(result)
    apply_accepted(raw, [decision.item_id for decision in result.decisions if decision.accepted])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The outer loop: learn from training runs, through a human gate.")
    parser.add_argument("step", choices=["propose", "gate"])
    args = parser.parse_args()
    propose() if args.step == "propose" else gate()
