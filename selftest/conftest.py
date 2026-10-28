"""Self-tests for the harness: no API calls, no human, no changes to your checkout.

    python -m pytest selftest

The whole session runs against a temporary copy of this repo (HARNESS_ROOT),
with the working tree committed there, so scenarios, the spine and the gate
can do real git and file work without touching yours. The model is a fake
that plays back a script; the human is a list of answers.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, List

import pytest

SOURCE = Path(__file__).resolve().parent.parent
IGNORE = shutil.ignore_patterns("venv", ".venv", "runs", ".harness", "__pycache__", ".idea", ".pytest_cache")

COPY = Path(tempfile.mkdtemp(prefix="harness-selftest-")).resolve() / "repo"
shutil.copytree(SOURCE, COPY, ignore=IGNORE)
subprocess.run(["git", "add", "-A"], cwd=COPY, check=True, capture_output=True)
subprocess.run(["git", "-c", "user.name=selftest", "-c", "user.email=selftest@example.invalid",
                "commit", "-q", "--allow-empty", "-m", "selftest snapshot"], cwd=COPY, check=True)
os.environ["HARNESS_ROOT"] = str(COPY)  # before any harness module is imported
os.environ.pop("HARNESS_INTENT", None)


@pytest.fixture
def repo() -> Path:
    return COPY


def green(name: str) -> str:
    """The committed, working version of checkout/<name>."""
    return subprocess.run(["git", "show", f"HEAD:checkout/{name}"], cwd=COPY,
                          capture_output=True, text=True, check=True).stdout


def usage(input_tokens: int = 100, output_tokens: int = 10) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


def write_call(call_id: str, name: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=call_id, name="write_file",
                           input={"path": f"checkout/{name}", "content": content})


def response(stop_reason: str, *content: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, usage=usage(), content=list(content))


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


class FakeClient:
    """Stands in for anthropic.Anthropic(): plays back responses and records every request."""

    def __init__(self, script: List[SimpleNamespace]) -> None:
        self.script = list(script)
        self.requests: List[dict] = []
        self.messages = self
        self.beta = self

    def create(self, **request):
        if "messages" in request:
            request = {**request, "messages": list(request["messages"])}  # the loop keeps appending to its list
        self.requests.append(request)
        return self.script.pop(0)


def scripted_human(answers: List[str]):
    """A `read` function for gate.ask_human that answers from a list, and fails if the list runs out."""
    remaining: Iterator[str] = iter(answers)

    def read(prompt: str) -> str:
        return next(remaining)

    return read
