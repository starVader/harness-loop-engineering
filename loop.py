import argparse
from typing import List, Optional

from anthropic.types import Message, ToolResultBlockParam, messages, MessageParam

from goal import GOALS, Goal
from spine import (
    STATUS_DONE,
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
from tools import TOOLS, execute_tool, run_tests
import anthropic

MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 16000
MAX_PASSES = 8

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

def run_tool_calls(response: Message) -> List[ToolResultBlockParam]:
    """Run every tool the model asked for; return one result per call, matched by id."""
    tool_results: List[ToolResultBlockParam] = []
    for block in response.content:
        if block.type != "tool_use":
            continue

        print(f"  tool_use  {block.name}({block.input})  id={block.id}")
        outcome = execute_tool(block.name, block.input)
        print(f"  ran       {block.name} -> {'ERROR' if outcome.is_error else 'ok'}")
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": outcome.content,
            "is_error": outcome.is_error,
        })
    return tool_results

def call_model(client: anthropic.Anthropic, messages: List[MessageParam]) -> Message:
    return client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=messages,
    )

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
    if spine is not None and spine.code_fingerprint != fingerprint_code():
        print("STALE SPINE: checkout/ changed since progress.json was saved; its record is no longer true. Starting fresh.")
        spine = None
    if spine is None:
        spine = new_spine(goal.name)
        save_spine(spine)
    return spine


def main(goal: Goal, fresh: bool, stop_after: Optional[int]) -> None:
    spine = open_spine(goal, fresh)
    if spine is None:
        return

    client = anthropic.Anthropic()
    task = TASK_TEMPLATE.format(goal=goal.description)
    if spine.passes:
        task += "\n" + progress_note(spine)
    messages: List[MessageParam] = [{"role": "user", "content": task}]
    total_input = total_output = 0
    first_pass = len(spine.passes) + 1
    print(f"=== goal={goal.name}: {goal.description}")
    if spine.passes:
        print(f"=== RESUMING from progress.json at pass {first_pass} (passes count toward the same cap of {MAX_PASSES})")

    for pass_number in range(first_pass, MAX_PASSES + 1):
        # Act: the model decides what to do next
        response = call_model(client, messages)
        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens
        print(f"--- pass {pass_number}/{MAX_PASSES}")
        print_response(response)
        messages.append({"role": "assistant", "content": response.content})

        # The model stopped asking for tools: it is claiming it is done
        if response.stop_reason != "tool_use":
            verdict = goal.is_met()
            if verdict is None:
                print(f"ACCEPTED ON THE MODEL'S WORD: stop_reason={response.stop_reason}; code cannot check this goal")
            elif verdict:
                print("DONE: model stopped and the goal is verified")
            else:
                print(f"STOPPED EARLY: stop_reason={response.stop_reason} but the goal is not met")
            spine.status = STATUS_DONE if verdict else STATUS_STOPPED
            save_spine(spine)
            break

        # Observe: run every tool, send all results back in one message
        tool_blocks = [block for block in response.content if block.type == "tool_use"]
        tool_results = run_tool_calls(response)
        messages.append({"role": "user", "content": tool_results})

        # Spine: record what this pass learned, before anything else can go wrong
        test_run = run_tests()
        spine.passes.append(PassRecord(
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
        ))

        # Goal: your code decides "done" when it can; otherwise it has to keep going
        verdict = goal.is_met()
        if verdict is None:
            print("  goal      cannot be checked by code; waiting for the model to stop")
        elif verdict:
            print(f"DONE: goal verified on pass {pass_number}")
            spine.status = STATUS_DONE
            save_spine(spine)
            break
        else:
            print("  goal      not met yet")
        save_spine(spine)

        if stop_after is not None and pass_number - first_pass + 1 >= stop_after:
            print(f"SIMULATED CRASH after {stop_after} pass(es): exiting without finishing; progress.json keeps status={STATUS_RUNNING}")
            return
    else:
        print(f"CAP HIT: {MAX_PASSES} passes used across all runs, goal not met")
        spine.status = STATUS_STOPPED
        save_spine(spine)

    # Outside observer: the same check for every goal, so runs can be compared
    observer = run_tests()
    print(f"observer: tests after the run: {observer.summary}")
    print(f"total tokens: input={total_input} output={total_output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the loop against one goal.")
    parser.add_argument("--goal", choices=sorted(GOALS), default="pytest")
    parser.add_argument("--fresh", action="store_true", help="ignore progress.json and start over")
    parser.add_argument("--stop-after", type=int, help="simulate a crash after N passes of this run")
    args = parser.parse_args()
    main(GOALS[args.goal], fresh=args.fresh, stop_after=args.stop_after)
