import argparse
from typing import List

from anthropic.types import Message, ToolResultBlockParam, messages, MessageParam

from goal import GOALS, Goal
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

def main(goal: Goal) -> None:
    client = anthropic.Anthropic()
    task = TASK_TEMPLATE.format(goal=goal.description)
    messages: List[MessageParam] = [{"role": "user", "content": task}]
    total_input = total_output = 0
    print(f"=== goal={goal.name}: {goal.description}")

    for pass_number in range(1, MAX_PASSES + 1):
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
            break

        # Observe: run every tool, send all results back in one message
        messages.append({"role": "user", "content": run_tool_calls(response)})

        # Goal: your code decides "done" when it can; otherwise it has to keep going
        verdict = goal.is_met()
        if verdict is None:
            print("  goal      cannot be checked by code; waiting for the model to stop")
        elif verdict:
            print(f"DONE: goal verified on pass {pass_number}")
            break
        else:
            print("  goal      not met yet")
    else:
        print(f"CAP HIT: {MAX_PASSES} passes used, goal not met")

    # Outside observer: the same check for every goal, so runs can be compared
    observer = run_tests()
    print(f"observer: tests after the run: {observer.summary}")
    print(f"total tokens: input={total_input} output={total_output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the loop against one goal.")
    parser.add_argument("--goal", choices=sorted(GOALS), default="pytest")
    main(GOALS[parser.parse_args().goal])
