from typing import List

from anthropic.types import Message, ToolResultBlockParam, messages, MessageParam

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

TASK = """
    Tests are failing in checkout service. Run all the tests in tests folder to see what is wrong.
    Read each failure carefully and fix the code. The task is done once every test in tests/ is passing.
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

def main():
    client = anthropic.Anthropic()
    messages: List[MessageParam] = [{"role": "user", "content": TASK}]
    total_input = total_output = 0

    for pass_number in range(1, MAX_PASSES + 1):
        # Act: the model decides what to do next
        response = call_model(client, messages)
        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens
        print(f"--- pass {pass_number}/{MAX_PASSES}")
        print_response(response)
        messages.append({"role": "assistant", "content": response.content})

        # The model stopped asking for tools: check whether it is right
        if response.stop_reason != "tool_use":
            test_run = run_tests()
            if test_run.exit_code == 0:
                print(f"DONE: model stopped and tests pass ({test_run.summary})")
            else:
                print(f"STOPPED EARLY: stop_reason={response.stop_reason} but tests fail ({test_run.summary})")
            break

        # Observe: run every tool, send all results back in one message
        messages.append({"role": "user", "content": run_tool_calls(response)})

        # Goal: your code decides "done", not the model
        test_run = run_tests()
        print(f"  goal      {test_run.summary}")
        if test_run.exit_code == 0:
            print(f"DONE: goal met on pass {pass_number}")
            break
    else:
        print(f"CAP HIT: {MAX_PASSES} passes used, goal not met")

    print(f"total tokens: input={total_input} output={total_output}")


if __name__ == "__main__":
    main()
