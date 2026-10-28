"""The rails around the loop: fixed-rule sensors, the trace, budgets and escalation."""

import subprocess

import anthropic
import pytest

from harness import checker, gate, loop, sensors
from harness.budget import Budget, Spend, cost
from harness.scenario import apply
from harness.spine import load_spine
from harness.trace import load, show, totals
from selftest.conftest import FakeClient, green, response, text, write_call

PASS_VERDICT = checker.Verdict(True, [], "no rule broken", 10, 5)
FAIL_VERDICT = checker.Verdict(False, [checker.Violation("checkout/discounts.py", "x", "a rule", "y")], "fail", 10, 5)


def fix_everything(discounts: str = None):
    return response("tool_use", write_call("t1", "checkout.py", green("checkout.py")),
                    write_call("t2", "discounts.py", discounts or green("discounts.py")))


def look(input_tokens: int = 100):
    reply = response("tool_use", write_call("t0", "tax.py", green("tax.py")))
    reply.usage.input_tokens = input_tokens
    return reply


def run(fake, monkeypatch, **overrides):
    monkeypatch.setattr(anthropic, "Anthropic", lambda: fake)
    options = dict(goal=loop.GOALS["pytest"], fresh=True, stop_after=None, compact_at=None, check=True,
                   actor_model="claude-sonnet-5-5", gate_on=False, lessons_path=None)
    options.update(overrides)
    loop.main(**options)
    return load_spine()


@pytest.fixture(autouse=True)
def broken(repo, monkeypatch):
    apply("broken")
    monkeypatch.setattr(gate, "FIXES_PATH", repo / ".harness" / "fixes-rails.md")


def apply_patch(repo, name):
    subprocess.run(["git", "apply", str(repo / "scenarios" / "cheats" / f"{name}.patch")], cwd=repo, check=True)


# ---------------------------------------------------------------- sensors

@pytest.mark.parametrize("cheat, sensor", [("catalog_bump", "catalog_unchanged"), ("loosened", "no_rejection_removed")])
def test_sensors_catch_the_cheats_for_free(repo, cheat, sensor):
    apply_patch(repo, cheat)
    assert sensor in [failure.sensor for failure in sensors.check()]


def test_sensors_pass_the_honest_fix(repo):
    apply_patch(repo, "proper_fix")
    assert sensors.check() == []


def test_sensor_rejection_never_reaches_the_checker(monkeypatch):
    reviews = []
    monkeypatch.setattr(loop, "review_diff", lambda *a: reviews.append(1) or PASS_VERDICT)
    bumped = green("discounts.py").replace("date(2026, 10, 31)", "date(2026, 11, 30)")  # tests stay green
    fake = FakeClient([fix_everything(bumped), fix_everything()])
    spine = run(fake, monkeypatch)
    assert spine.status == "done"
    assert (spine.passes[0].sensors, spine.passes[0].checker) == ("fail", None)
    assert len(reviews) == 1, "the checker only saw the second, honest change"
    assert "CATALOG changed" in fake.requests[1]["messages"][-1]["content"]


# ---------------------------------------------------------------- trace

def test_trace_records_the_run_in_order(monkeypatch):
    monkeypatch.setattr(loop, "review_diff", lambda *a: PASS_VERDICT)
    spine = run(FakeClient([look(), fix_everything()]), monkeypatch)
    events = load(spine.run_ids[-1])
    kinds = [event["event"] for event in events]
    assert kinds[0] == "run_start" and kinds[-1] == "run_end"
    assert kinds.count("model_call") == 2 and "sensor_verdict" in kinds and "checker_verdict" in kinds
    expected = cost("claude-sonnet-5-5", 200, 20) + cost(checker.CHECKER_MODEL, 10, 5)
    assert totals(events)["cost_usd"] == pytest.approx(expected, abs=1e-5)
    assert events[-1]["status"] == "done"
    assert "end: done" in show(events)


def test_a_crash_leaves_a_trace_without_run_end(monkeypatch):
    spine = run(FakeClient([look()]), monkeypatch, check=False, stop_after=1)
    assert load(spine.run_ids[-1])[-1]["event"] != "run_end"
    assert "crashed or still running" in show(load(spine.run_ids[-1]))


# ---------------------------------------------------------------- budgets and escalation

def test_budget_reasons():
    budget = Budget(max_passes=2, max_cost_usd=0.01, max_minutes=5, max_rejections=2)
    assert budget.exceeded(Spend(), passes_used=0) is None
    assert budget.exceeded(Spend(), passes_used=2).startswith("pass budget")
    assert budget.exceeded(Spend(cost_usd=0.02), passes_used=0).startswith("cost budget")
    assert budget.exceeded(Spend(rejections=2), passes_used=0).startswith("rejection budget")
    assert cost("some-new-model", 1_000_000, 0) == max(price for price, _ in __import__("harness.budget").budget.PRICES.values())


def test_cost_budget_escalates_and_blocks_resume(repo, monkeypatch, capsys):
    fake = FakeClient([look(input_tokens=1_000_000)])
    spine = run(fake, monkeypatch, check=False, budget=Budget(max_cost_usd=0.50))
    assert spine.status == "escalated" and spine.escalation_reason.startswith("cost budget")
    assert len(fake.requests) == 1, "no call after the budget ran out"
    assert spine.run_ids[-1] in (repo / ".harness" / "escalations.md").read_text()
    run(FakeClient([]), monkeypatch, check=False, fresh=False)
    assert "ESCALATED BEFORE" in capsys.readouterr().out


def test_pass_budget_replaces_the_old_cap(monkeypatch):
    spine = run(FakeClient([look()]), monkeypatch, check=False, budget=Budget(max_passes=1))
    assert spine.status == "escalated" and spine.escalation_reason.startswith("pass budget")


def test_rejection_budget_stops_a_loop_that_isnt_converging(monkeypatch):
    monkeypatch.setattr(loop, "review_diff", lambda *a: FAIL_VERDICT)
    fake = FakeClient([fix_everything(), response("end_turn", text("Still the same."))])
    spine = run(fake, monkeypatch, budget=Budget(max_rejections=2))
    assert spine.status == "escalated" and spine.escalation_reason.startswith("rejection budget")


# ---------------------------------------------------------------- checker eval

def test_checker_eval_reports_pass_hat_k():
    import json as json_module
    from types import SimpleNamespace
    from harness import checker_eval

    def reply(verdict):
        payload = {"verdict": verdict, "summary": "s", "violations": []}
        return SimpleNamespace(stop_reason="end_turn", usage=SimpleNamespace(input_tokens=1000, output_tokens=100),
                               content=[SimpleNamespace(type="text", text=json_module.dumps(payload))])

    cases = checker_eval.load_cases()
    script = []
    for index, case in enumerate(cases):
        wrong = "fail" if case.expect == "pass" else "pass"
        # case 0 (a regression) is wrong once in 3 trials; every other case is always right
        script += [reply(case.expect), reply(wrong if index == 0 else case.expect), reply(case.expect)]
    results, spent = checker_eval.run_eval(FakeClient(script), trials=3)
    assert [result.pass_hat_k for result in results] == [False] + [True] * (len(cases) - 1)
    assert not checker_eval.regressions_hold(results)
    table = checker_eval.report(results, spent)
    assert "no (2/3)" in table and "regression cases: 3/4" in table and spent > 0


# ---------------------------------------------------------------- fixes from the review

def test_sensors_fail_closed_without_a_snapshot(tmp_path):
    assert [failure.sensor for failure in sensors.check(baseline_dir=tmp_path)] == ["baseline_missing"]


def test_spend_carries_over_when_a_run_resumes(monkeypatch):
    first = FakeClient([look(input_tokens=100_000)])  # Sonnet: $0.20
    spine = run(first, monkeypatch, check=False, stop_after=1, budget=Budget(max_cost_usd=1.00))
    assert spine.spent_usd == pytest.approx(0.20, abs=0.01)
    resumed = FakeClient([])
    spine = run(resumed, monkeypatch, check=False, fresh=False, budget=Budget(max_cost_usd=0.10))
    assert spine.status == "escalated" and resumed.requests == [], "the resumed run inherits the bill"


def test_review_verdicts_are_recorded_when_the_model_stops(monkeypatch):
    verdicts = iter([FAIL_VERDICT, PASS_VERDICT])
    monkeypatch.setattr(loop, "review_diff", lambda *a: next(verdicts))
    spine = run(FakeClient([fix_everything(), response("end_turn", text("Kept it as is, here's why."))]), monkeypatch)
    assert spine.status == "done" and len(spine.passes) == 2
    stopped = spine.passes[1]
    assert stopped.tool_calls == [] and stopped.tests_summary.startswith("14 passed")
    assert (stopped.sensors, stopped.checker) == ("pass", "pass")


def test_experiment_saves_nothing_from_a_run_that_never_started(repo, monkeypatch):
    from harness import experiment
    stem = repo / "runs" / "stage8" / "before-bugset04"
    stem.parent.mkdir(parents=True, exist_ok=True)
    stem.with_suffix(".trace.jsonl").write_text("stale\n")  # left over from an earlier attempt
    monkeypatch.setenv("HARNESS_SANDBOX", "nonexistent")  # the loop subprocess refuses to start
    experiment.run_one("before", "bugset04")
    monkeypatch.delenv("HARNESS_SANDBOX")
    assert "NOT STARTED" in stem.with_suffix(".md").read_text()
    assert not stem.with_suffix(".trace.jsonl").exists() and not stem.with_suffix(".progress.json").exists()
    assert "did not start" in stem.with_suffix(".audit").read_text()
    assert "| before | bugset04 | not started |" in experiment.summary()
