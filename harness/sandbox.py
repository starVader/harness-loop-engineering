"""Where actor-written code runs.

The actor can only write checkout/*.py, but pytest then *imports* those files,
so whatever the model wrote runs with your permissions. Every test run in the
harness (the visible tests and the audit) goes through run_pytest here, so
there is exactly one place that decides where that code executes.

    local   (default) a subprocess on this machine: fast, no setup, not isolated
    docker  a throwaway container: no network, read-only code, capped memory,
            CPU and processes, a non-root user. Fails closed if Docker or the
            image is missing; it never falls back to local by itself.

    python -m harness.sandbox build     # build the image once (sandbox/Dockerfile)
    python -m harness.sandbox check     # is the chosen mode ready?
"""

import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from typing import List, Sequence

from harness.paths import REPO_ROOT

MODES = ("local", "docker")
IMAGE = "harness-sandbox:1"
TIMEOUT_SECONDS = 60
OUTPUT_TAIL_LINES = 60
# What the code under test may see, read-only: product code, the visible tests, and (for the audit) its tests
MOUNTS = ("checkout", "tests", "scenarios/audit")


@dataclass(frozen=True)
class TestRun:
    exit_code: int
    summary: str
    output_tail: str


class SandboxUnavailable(Exception):
    """The sandbox asked for can't run. Nothing is executed instead."""


def mode() -> str:
    chosen = os.environ.get("HARNESS_SANDBOX", "local")
    if chosen not in MODES:
        raise SandboxUnavailable(f"HARNESS_SANDBOX={chosen!r}; use one of {', '.join(MODES)}")
    return chosen


def pytest_args(target: str, extra: Sequence[str]) -> List[str]:
    return ["-m", "pytest", "-q", "-p", "no:cacheprovider", *extra, target]


def docker_command(target: str, extra: Sequence[str], name: str) -> List[str]:
    command = [
        "docker", "run", "--rm", "--name", name,
        "--network", "none", "--read-only", "--tmpfs", "/tmp",
        "--memory", "512m", "--cpus", "1", "--pids-limit", "128",
        "--user", "1000:1000", "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--workdir", "/w",
    ]
    for mount in MOUNTS:
        if (REPO_ROOT / mount).is_dir():
            command += ["--volume", f"{REPO_ROOT / mount}:/w/{mount}:ro"]
    return command + [IMAGE, "python", *pytest_args(target, extra)]


def ensure_ready() -> None:
    """Fail before the run starts, not halfway through it."""
    if mode() == "local":
        return
    try:
        found = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise SandboxUnavailable(f"docker is not available ({exc})") from exc
    if found.returncode != 0:
        raise SandboxUnavailable(f"image {IMAGE} not found (is Docker running?); build it: python -m harness.sandbox build")


def warning() -> str:
    """One line for the top of a run, so nobody forgets where the actor's code executes."""
    if mode() == "local":
        return "WARNING: actor-written code runs unsandboxed on this machine (use --sandbox docker)"
    return f"sandbox: docker ({IMAGE}, no network, read-only code)"


def run_pytest(target: str, extra: Sequence[str] = ("--tb=short",)) -> TestRun:
    """Run pytest on `target` (a path relative to the repo) in the chosen sandbox."""
    container = f"harness-{uuid.uuid4().hex[:8]}"
    if mode() == "local":
        command = [sys.executable, *pytest_args(target, extra)]
    else:
        ensure_ready()
        command = docker_command(target, extra, container)
    try:
        completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        if mode() == "docker":
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        return TestRun(exit_code=-1, summary="timed out", output_tail="")
    lines = (completed.stdout + completed.stderr).strip().splitlines()
    return TestRun(
        exit_code=completed.returncode,
        summary=lines[-1] if lines else "no output",
        output_tail="\n".join(lines[-OUTPUT_TAIL_LINES:]),
    )


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "check"
    if step == "build":
        sys.exit(subprocess.run(["docker", "build", "-t", IMAGE, str(REPO_ROOT / "sandbox")]).returncode)
    elif step == "check":
        try:
            ensure_ready()
            print(f"ready: {warning()}")
        except SandboxUnavailable as exc:
            sys.exit(f"not ready: {exc}")
    else:
        sys.exit("usage: python -m harness.sandbox {build | check}")
