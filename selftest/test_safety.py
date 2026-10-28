"""Safety rails: where actor code runs, and what scenario apply refuses to throw away."""

import subprocess

import pytest

from harness import sandbox
from harness.audit import broken_rules
from harness.scenario import CURRENT_FILE, UnsavedChanges, apply
from harness.tools import run_tests


def docker_ready() -> bool:
    try:
        return subprocess.run(["docker", "image", "inspect", sandbox.IMAGE], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


def test_docker_command_is_locked_down(repo):
    command = sandbox.docker_command("tests/", ("--tb=short",), "harness-test")
    joined = " ".join(command)
    for flag in ("--network none", "--read-only", "--memory 512m", "--pids-limit 128", "--user 1000:1000"):
        assert flag in joined
    assert f"{repo / 'checkout'}:/w/checkout:ro" in command
    assert not any(":/w/harness" in part or "/w/.git" in part for part in command), "the harness never enters the box"


def test_unknown_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("HARNESS_SANDBOX", "chroot")
    with pytest.raises(sandbox.SandboxUnavailable):
        run_tests()


def test_docker_without_the_image_fails_closed(monkeypatch):
    monkeypatch.setenv("HARNESS_SANDBOX", "docker")
    monkeypatch.setattr(sandbox, "IMAGE", "harness-sandbox:does-not-exist")
    with pytest.raises(sandbox.SandboxUnavailable):
        run_tests()


def test_local_mode_says_it_is_unsandboxed(monkeypatch):
    monkeypatch.delenv("HARNESS_SANDBOX", raising=False)
    assert sandbox.warning().startswith("WARNING")


@pytest.mark.skipif(not docker_ready(), reason="Docker or the harness-sandbox image is not available")
def test_tests_and_audit_run_in_docker(monkeypatch):
    monkeypatch.setenv("HARNESS_SANDBOX", "docker")
    apply("broken")
    assert run_tests().summary.startswith("4 failed, 10 passed")
    apply("bugset02")
    assert len(broken_rules()) == 3


def test_apply_refuses_to_discard_your_edits(repo):
    apply("green")
    CURRENT_FILE.unlink()  # as in a fresh clone: no scenario applied yet
    (repo / "checkout" / "tax.py").write_text("# my own edit\n")
    with pytest.raises(UnsavedChanges):
        apply("broken")
    apply("broken", force=True)
    assert "my own edit" not in (repo / "checkout" / "tax.py").read_text()
