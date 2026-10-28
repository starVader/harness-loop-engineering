"""The loop: goal -> act -> observe -> adjust, and every layer built around it.

    python -m harness.scenario apply broken
    python -m harness.loop --fresh

Every layer is on by default and each one has a switch, so any stage of the
demo is this file with some layers turned off:

    stage 1  bare loop      --no-check --no-gate --no-compact
    stage 2  goal           --goal self  (the model decides "done")
    stage 3  spine          --stop-after N, then run again without --fresh
    stage 4  context        --compact-at N / --no-compact
    stage 5  checker        on unless --no-check
    stage 6  intent         --intent scenarios/intent/no_rules.md
    stage 7  human gate     on unless --no-gate
    stage 8  lessons        --lessons FILE  (see harness/experiment.py)

Around every stage, the safety rails stay on:

    sandbox      --sandbox docker  (where actor-written code runs; default local, with a warning)
    fixed rules  on unless --no-sensors  (free deterministic checks, before the checker)
    budgets      --max-passes / --max-cost / --max-minutes / --max-rejections -> ESCALATED
    trace        every event in .harness/traces/<run_id>.jsonl  (python -m harness.trace show latest)
"""

import argparse
import hashlib
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from anthropic.types import Message, MessageParam, ToolResultBlockParam

from harness import sensors
from harness.budget import Budget, Spend
from harness.checker import CHECKER_MODEL, CheckerUnavailable, feedback_for_actor, print_verdict, review_diff
from harness.gate import GateUnavailable, ask_human, hunks, record, unexplained
from harness.gate import feedback_for_actor as gate_feedback_for_actor, print_result as print_gate_result
from harness.goal import GOALS, Goal
from harness.paths import STATE_DIR, intent_path
from harness.sandbox import SandboxUnavailable, ensure_ready, mode as sandbox_mode, warning as sandbox_warning
from harness.scenario import NoScenario, current, current_diff
from harness.spine import (
    STATUS_DONE,
    STATUS_ESCALATED,
    STATUS_RUNNING,
    STATUS_STOPPED,
    PassRecord,
    Spine,
    failing_tests_from,
    fingerprint_code,
    load_spine,
    new_spine,
    progress_note,
    save_spine,
)
from harness.tools import TOOLS, execute_tool, run_tests
from harness.trace import Trace
import anthropic

ACTOR_MODELS = {"sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"}
MAX_TOKENS = 16000
ESCALATIONS_PATH = STATE_DIR / "escalations.md"
COMPACT_AT_INPUT_TOKENS = 5_000  # low on purpose: these runs peak around 8K

SYSTEM_PROMPT = """
    This system is a checkout service. It is at the heart of ordering system where real money is involved in customer checkouts. 
    Your job is to find and fix bugs in the code so it behaves the way the tests describe.
    The tests define the correct behaviour and are read-only; all fixes go in checkout/. Run tests before you write code.
    Whenever you are unsure run the associated test to find more information, once done state your assumptions.
"""

# Stage 2: only the goal sentence changes between runs; everything else is held constant.
TASK_TEMPLATE = """
    You are working on the checkout service in this repository.
    Your goal: {goal}
    When finished, summarise each change and why.
"""


def print_response(response: anthropic.types.Message) -> None:
    print(f"stop_reason: {response.stop_reason}")
    for block in response.content:
        if block.type == "tool_use":
            print(f"  tool_use  {block.name}({block.input})  id={block.id}")
        elif block.type == "text":
            print(f"  text      {block.text}")
        # thinking blocks are skipped: their text is empty by default
    print(f"tokens: input={response.usage.input_tokens} output={response.usage.output_tokens}")

@dataclass
class Run:
    """One process driving the loop: who it talks to, what it may spend, which checks are on, where it writes."""
    client: anthropic.Anthropic
    trace: Trace
    spend: Spend
    budget: Budget
    check: bool
    gate_on: bool
    sensors_on: bool

def run_tool_calls(run: Run, response: Message, pass_number: int) -> List[ToolResultBlockParam]:
    """Run every tool the model asked for; return one result per call, matched by id."""
    tool_results: List[ToolResultBlockParam] = []
    for block in response.content:
        if block.type != "tool_use":
            continue

        print(f"  tool_use  {block.name}({block.input})  id={block.id}")
        started = time.monotonic()
        outcome = execute_tool(block.name, block.input)
        print(f"  ran       {block.name} -> {'ERROR' if outcome.is_error else 'ok'}")
        run.trace.event("tool_call", pass_number, name=block.name, path=block.input.get("path"),
                        is_error=outcome.is_error, ms=round((time.monotonic() - started) * 1000))
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": outcome.content,
            "is_error": outcome.is_error,
        })
    return tool_results

def system_prompt(lessons_path: Optional[Path]) -> str:
    """The actor's standing instructions, plus any lessons a human accepted from the outer loop."""
    if lessons_path is None:
        return SYSTEM_PROMPT
    lessons = lessons_path.read_text().strip()
    print(f"lessons: {len(lessons.splitlines())} line(s) from {lessons_path.name} added to the system prompt")
    return f"{SYSTEM_PROMPT}\n<lessons from past runs>\n{lessons}\n</lessons from past runs>"

def call_model(client: anthropic.Anthropic, messages: List[MessageParam], model: str, system: str) -> Message:
    return client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=TOOLS,
        messages=messages,
    )

def compact_history(task: str, spine: Spine) -> List[MessageParam]:
    """Start a fresh conversation: the task plus what the spine says was learned."""
    briefing = progress_note(spine, reason="to keep the context small")
    return [{"role": "user", "content": f"{task}\n\n{briefing}"}]

def sensor_feedback(run: Run, pass_number: int) -> Optional[str]:
    """Fixed rules, checked by code: free, so they go before anything that costs money or attention."""
    if not run.sensors_on:
        print("sensors: off (--no-sensors)")
        return None
    failures = sensors.check()
    print(f"sensors: {'FAIL' if failures else 'PASS'} (fixed rules, no model)")
    for failure in failures:
        print(f"  violation  {failure.sensor}: {failure.message}")
    run.trace.event("sensor_verdict", pass_number, verdict="fail" if failures else "pass",
                    failures=[failure.sensor for failure in failures])
    return sensors.feedback_for_actor(failures) if failures else None

def checker_feedback(run: Run, pass_number: int) -> Optional[str]:
    """Review the loop's change against INTENT.md. None = accepted; a string = the rejection to send back."""
    if not run.check:
        print("checker: off (--no-check)")
        return None
    verdict = review_diff(run.client, current_diff(), intent_path().read_text())
    spent = run.spend.add(CHECKER_MODEL, verdict.input_tokens, verdict.output_tokens)
    print_verdict(verdict)
    run.trace.event("checker_verdict", pass_number, verdict="pass" if verdict.passed else "fail",
                    model=CHECKER_MODEL, violations=[violation.change for violation in verdict.violations],
                    input_tokens=verdict.input_tokens, output_tokens=verdict.output_tokens, cost_usd=spent)
    return None if verdict.passed else feedback_for_actor(verdict)

def gate_feedback(run: Run, pass_number: int) -> Optional[str]:
    """Ask the human to explain each block nobody has explained yet. None = accepted; a string = the rejection."""
    if not run.gate_on:
        print("gate: off (--no-gate)")
        return None
    pending = unexplained(hunks(current_diff()))
    if not pending:
        print("gate: PASS (every block is already explained)")
        run.trace.event("gate_decision", pass_number, verdict="pass", asked=0)
        return None
    started = time.monotonic()
    result = ask_human(pending)
    record(result)
    print_gate_result(result)
    run.trace.event("gate_decision", pass_number, verdict="pass" if result.passed else "fail", asked=len(pending),
                    rejected=[decision.title for decision in result.rejections],
                    seconds=round(time.monotonic() - started, 1))
    return None if result.passed else gate_feedback_for_actor(result)

@dataclass(frozen=True)
class Review:
    rejection: Optional[str]  # None = accepted
    rejected_by: str  # "SENSOR", "CHECKER" or "GATE" when rejected
    sensors: Optional[str]  # "pass" / "fail", None when off or not reached
    checker: Optional[str]
    gate: Optional[str]

def review_change(run: Run, pass_number: int) -> Review:
    """The tests passed. Cheapest check first: fixed rules (free), checker (cents), human (minutes).

    Raises CheckerUnavailable or GateUnavailable: either one means the change is not accepted.
    """
    def verdict(on: bool, rejection: Optional[str]) -> Optional[str]:
        return None if not on else ("pass" if rejection is None else "fail")

    rejection = sensor_feedback(run, pass_number)
    sensor_mark = verdict(run.sensors_on, rejection)
    if rejection is not None:
        run.spend.rejections += 1
        return Review(rejection, "SENSOR", sensor_mark, checker=None, gate=None)
    rejection = checker_feedback(run, pass_number)
    checker_mark = verdict(run.check, rejection)
    if rejection is not None:
        run.spend.rejections += 1
        return Review(rejection, "CHECKER", sensor_mark, checker_mark, gate=None)
    rejection = gate_feedback(run, pass_number)
    if rejection is not None:
        run.spend.rejections += 1
    return Review(rejection, "GATE" if rejection is not None else "", sensor_mark, checker_mark,
                  verdict(run.gate_on, rejection))

def print_rejection(review: Review) -> None:
    if review.rejected_by == "SENSOR":
        print("FIXED RULE REJECTED: the goal is met but the change breaks a rule code can check; sending it back")
    elif review.rejected_by == "CHECKER":
        print("CHECKER REJECTED: the goal is met but the change breaks INTENT.md; sending the violations back")
    else:
        print("GATE REJECTED: the goal is met but the human did not accept part of the change; sending their reasons back")

def record_pass(spine: Spine, pass_number: int, response: Message, tool_blocks: list,
                tool_results: List[ToolResultBlockParam]) -> PassRecord:
    """Spine: what this pass did and where the tests stand, appended before anything else can go wrong."""
    test_run = run_tests()
    record = PassRecord(
        pass_number=pass_number,
        tool_calls=[f"{block.name}({block.input.get('path', '')})" for block in tool_blocks],
        files_written=[
            block.input["path"]
            for block, result in zip(tool_blocks, tool_results)
            if block.name == "write_file" and not result["is_error"]
        ],
        failing_tests=failing_tests_from(test_run.output_tail),
        tests_summary=test_run.summary,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    spine.passes.append(record)
    return record

def mark_review(record: PassRecord, review: "Review") -> None:
    record.sensors, record.checker, record.gate = review.sensors, review.checker, review.gate

def save(run: Run, spine: Spine) -> None:
    """Save the spine with what this spine has cost so far, so a resumed run inherits the bill."""
    spine.spent_usd = round(run.spend.cost_usd, 6)
    save_spine(spine)

def escalate(run: Run, spine: Spine, reason: str, pass_number: int, scenario: str) -> None:
    """A budget ran out. Stop in a defined state and leave a note a human will find."""
    print(f"ESCALATED ({reason}): needs a human")
    run.trace.event("budget_exceeded", pass_number, reason=reason)
    spine.status = STATUS_ESCALATED
    spine.escalation_reason = reason
    save(run, spine)
    run.trace.event("escalation", pass_number, reason=reason)
    latest = spine.passes[-1] if spine.passes else None
    ESCALATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ESCALATIONS_PATH.open("a") as note:
        note.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} run {run.trace.run_id} (scenario {scenario})\n"
                   f"- reason: {reason}\n"
                   f"- tests at the last pass: {latest.tests_summary if latest else 'not run'}\n"
                   f"- still failing: {', '.join(latest.failing_tests) if latest and latest.failing_tests else 'none'}\n"
                   f"- spend: ${run.spend.cost_usd:.4f}, {run.spend.minutes:.1f} min, "
                   f"{run.spend.rejections} rejected review(s)\n")

def open_spine(goal: Goal, fresh: bool) -> Optional[Spine]:
    """Decide whether to resume. Returns None when the run must not start at all."""
    spine = None if fresh else load_spine()
    if spine is not None and spine.goal != goal.name:
        print(f"spine: progress.json is for goal={spine.goal}; starting fresh")
        spine = None
    if spine is not None and spine.status == STATUS_DONE:
        print("ALREADY DONE: progress.json says this goal was verified. Rerunning is a no-op; use --fresh to start over.")
        return None
    if spine is not None and spine.status == STATUS_STOPPED:
        print("STOPPED BEFORE: the last run stopped without verifying the goal. Use --fresh to start over.")
        return None
    if spine is not None and spine.status == STATUS_ESCALATED:
        print(f"ESCALATED BEFORE ({spine.escalation_reason}): a human should look first "
              f"(.harness/escalations.md). Use --fresh to start over.")
        return None
    if spine is not None and spine.code_fingerprint != fingerprint_code():
        print("STALE SPINE: checkout/ changed since progress.json was saved; its record is no longer true. Starting fresh.")
        spine = None
    if spine is None:
        spine = new_spine(goal.name)
        save_spine(spine)
    return spine


def main(goal: Goal, fresh: bool, stop_after: Optional[int], compact_at: Optional[int], check: bool,
         actor_model: str, gate_on: bool, lessons_path: Optional[Path], sensors_on: bool = True,
         budget: Budget = Budget()) -> None:
    try:
        scenario = current()
        ensure_ready()
    except (NoScenario, SandboxUnavailable) as exc:
        print(f"NOT STARTED: {exc}")
        return
    spine = open_spine(goal, fresh)
    if spine is None:
        return

    run = Run(client=anthropic.Anthropic(), trace=Trace(), spend=Spend(cost_usd=spine.spent_usd), budget=budget,
              check=check, gate_on=gate_on, sensors_on=sensors_on)
    spine.run_ids.append(run.trace.run_id)
    save(run, spine)
    system = system_prompt(lessons_path)
    # base_task never carries a briefing, so compaction can't stack an old one under a new one
    base_task = TASK_TEMPLATE.format(goal=goal.description)
    task = base_task
    if spine.passes:
        task += "\n" + progress_note(spine, reason="after an interruption")
    messages: List[MessageParam] = [{"role": "user", "content": task}]
    first_pass = len(spine.passes) + 1
    print(sandbox_warning())
    print(f"=== goal={goal.name}: {goal.description}  actor={actor_model}  scenario={scenario}  "
          f"intent={intent_path().name}  run={run.trace.run_id}")
    run.trace.event("run_start", scenario=scenario, goal=goal.name, actor_model=actor_model,
                    checker_model=CHECKER_MODEL if check else None, sandbox=sandbox_mode(),
                    intent=str(intent_path()), intent_sha=hashlib.sha256(intent_path().read_bytes()).hexdigest()[:12],
                    lessons=str(lessons_path) if lessons_path else None, budget=asdict(budget),
                    switches={"sensors": sensors_on, "checker": check, "gate": gate_on, "compact_at": compact_at},
                    resumed_after_pass=first_pass - 1)
    if spine.passes:
        print(f"=== RESUMING from progress.json at pass {first_pass} "
              f"(passes count toward the same budget of {budget.max_passes})")

    pass_number = first_pass - 1
    while True:
        # Budget: checked by the harness before every call, never left to the model
        reason = budget.exceeded(run.spend, passes_used=pass_number)
        if reason is not None:
            escalate(run, spine, reason, pass_number, scenario)
            break
        pass_number += 1

        # Act: the model decides what to do next
        response = call_model(run.client, messages, actor_model, system)
        spent = run.spend.add(actor_model, response.usage.input_tokens, response.usage.output_tokens)
        print(f"--- pass {pass_number}/{budget.max_passes}")
        print_response(response)
        run.trace.event("model_call", pass_number, model=actor_model, stop_reason=response.stop_reason,
                        input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
                        cost_usd=spent, tools=[block.name for block in response.content if block.type == "tool_use"])
        messages.append({"role": "assistant", "content": response.content})

        # Budget again: that call may have gone over; if so, nothing it asked for runs
        reason = budget.overspent(run.spend)
        if reason is not None:
            escalate(run, spine, reason, pass_number, scenario)
            break

        # The model stopped asking for tools: it is claiming it is done
        if response.stop_reason != "tool_use":
            record = record_pass(spine, pass_number, response, [], [])
            verdict = goal.is_met()
            run.trace.event("goal_check", pass_number, met=verdict, tests=record.tests_summary, after="model stopped")
            if verdict is None:
                print(f"ACCEPTED ON THE MODEL'S WORD: stop_reason={response.stop_reason}; code cannot check this goal")
            elif not verdict:
                print(f"STOPPED EARLY: stop_reason={response.stop_reason} but the goal is not met")
            else:
                try:
                    review = review_change(run, pass_number)
                except (CheckerUnavailable, GateUnavailable) as exc:
                    print(f"REVIEW UNAVAILABLE: {exc}; not accepting the change")
                    spine.status = STATUS_STOPPED
                    save(run, spine)
                    break
                mark_review(record, review)
                if review.rejection is not None:
                    print_rejection(review)
                    save(run, spine)
                    messages.append({"role": "user", "content": review.rejection})
                    continue
                print("DONE: model stopped, the goal is verified and the change is accepted")
            spine.status = STATUS_DONE if verdict else STATUS_STOPPED
            save(run, spine)
            break

        # Observe: run every tool, send all results back in one message
        tool_blocks = [block for block in response.content if block.type == "tool_use"]
        tool_results = run_tool_calls(run, response, pass_number)
        messages.append({"role": "user", "content": tool_results})

        # Spine: record what this pass learned, before anything else can go wrong
        record = record_pass(spine, pass_number, response, tool_blocks, tool_results)

        # Goal: your code decides "done" when it can; otherwise it has to keep going
        rejection: Optional[str] = None
        verdict = goal.is_met()
        run.trace.event("goal_check", pass_number, met=verdict, tests=record.tests_summary)
        if verdict is None:
            print("  goal      cannot be checked by code; waiting for the model to stop")
        elif verdict:
            # Review: the tests say it works; fixed rules and the checker say it's allowed; the human says it's understood
            try:
                review = review_change(run, pass_number)
            except (CheckerUnavailable, GateUnavailable) as exc:
                print(f"REVIEW UNAVAILABLE: {exc}; not accepting the change")
                spine.status = STATUS_STOPPED
                save(run, spine)
                break
            mark_review(record, review)
            rejection = review.rejection
            if rejection is None:
                print(f"DONE: goal verified on pass {pass_number} and the change is accepted")
                spine.status = STATUS_DONE
                save(run, spine)
                break
            print_rejection(review)
        else:
            print("  goal      not met yet")
        save(run, spine)

        # Compact: only here, where the history is complete and the spine holds this pass
        if compact_at is not None and response.usage.input_tokens > compact_at:
            print(f"COMPACTED after pass {pass_number}: last call was {response.usage.input_tokens} input tokens "
                  f"(limit {compact_at}); restarting the conversation from the spine")
            run.trace.event("compaction", pass_number, reason=f"{response.usage.input_tokens} > {compact_at}")
            spine.passes[-1].compacted = True
            save(run, spine)
            messages = compact_history(base_task, spine)

        # A rejection goes in after any compaction, so forgetting can't drop it
        if rejection is not None:
            messages.append({"role": "user", "content": rejection})

        if stop_after is not None and pass_number - first_pass + 1 >= stop_after:
            print(f"SIMULATED CRASH after {stop_after} pass(es): exiting without finishing; progress.json keeps status={STATUS_RUNNING}")
            return

    # Outside observer: the same check for every goal, so runs can be compared
    observer = run_tests()
    print(f"observer: tests after the run: {observer.summary}")
    print(f"total tokens: input={run.spend.input_tokens} output={run.spend.output_tokens} "
          f"cost=${run.spend.cost_usd:.4f} (actor + checker)  trace: python -m harness.trace show {run.trace.run_id}")
    run.trace.event("run_end", pass_number, status=spine.status, observer=observer.summary,
                    input_tokens_total=run.spend.input_tokens, output_tokens_total=run.spend.output_tokens,
                    cost_usd_total=round(run.spend.cost_usd, 6), minutes=round(run.spend.minutes, 2),
                    rejections=run.spend.rejections)


if __name__ == "__main__":
    defaults = Budget()
    parser = argparse.ArgumentParser(description="Run the loop against one goal.")
    parser.add_argument("--goal", choices=sorted(GOALS), default="pytest")
    parser.add_argument("--fresh", action="store_true", help="ignore the spine (.harness/progress.json) and start over")
    parser.add_argument("--stop-after", type=int, help="simulate a crash after N passes of this run")
    parser.add_argument("--no-compact", action="store_true", help="never compact (the baseline for stage 4)")
    parser.add_argument("--compact-at", type=int, default=COMPACT_AT_INPUT_TOKENS,
                        help=f"compact once a call's input tokens exceed this (default {COMPACT_AT_INPUT_TOKENS})")
    parser.add_argument("--no-sensors", action="store_true", help="skip the fixed rules (free deterministic checks)")
    parser.add_argument("--no-check", action="store_true", help="skip the checker (accept on tests alone)")
    parser.add_argument("--actor-model", choices=sorted(ACTOR_MODELS), default="sonnet", help="model that writes the fixes")
    parser.add_argument("--no-gate", action="store_true", help="skip the human gate (unattended runs only)")
    parser.add_argument("--intent", type=Path, help="the intent the actor and checker read as INTENT.md (default INTENT.md)")
    parser.add_argument("--lessons", type=Path, help="lessons appended to the actor's system prompt (stage 8)")
    parser.add_argument("--sandbox", choices=("local", "docker"), help="where actor-written code runs (default local)")
    parser.add_argument("--max-passes", type=int, default=defaults.max_passes)
    parser.add_argument("--max-cost", type=float, default=defaults.max_cost_usd, help="dollars, actor + checker")
    parser.add_argument("--max-minutes", type=float, default=defaults.max_minutes)
    parser.add_argument("--max-rejections", type=int, default=defaults.max_rejections,
                        help="rejected reviews before the run is handed to a human")
    args = parser.parse_args()
    if args.compact_at <= 0:
        parser.error("--compact-at must be a positive number of tokens; use --no-compact to turn compaction off")
    for path in (args.intent, args.lessons):
        if path is not None and not path.is_file():
            parser.error(f"{path} does not exist")
    if args.intent is not None:
        os.environ["HARNESS_INTENT"] = str(args.intent.resolve())
    if args.sandbox is not None:
        os.environ["HARNESS_SANDBOX"] = args.sandbox
    main(
        GOALS[args.goal],
        fresh=args.fresh,
        stop_after=args.stop_after,
        compact_at=None if args.no_compact else args.compact_at,
        check=not args.no_check,
        actor_model=ACTOR_MODELS[args.actor_model],
        gate_on=not args.no_gate,
        lessons_path=args.lessons,
        sensors_on=not args.no_sensors,
        budget=Budget(args.max_passes, args.max_cost, args.max_minutes, args.max_rejections),
    )
