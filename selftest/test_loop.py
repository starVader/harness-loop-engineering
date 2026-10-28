"""The whole loop and the outer loop, end to end, with a fake model and a scripted human."""

import json

import anthropic
import pytest

from harness import checker, experiment, gate, loop, reflect
from harness.scenario import apply
from harness.spine import load_spine
from selftest.conftest import FakeClient, green, response, scripted_human, text, write_call

FIX_EVERYTHING = lambda: response(  # noqa: E731
    "tool_use",
    write_call("t1", "checkout.py", green("checkout.py")),
    write_call("t2", "discounts.py", green("discounts.py")),
)
PASS_VERDICT = checker.Verdict(True, [], "no rule broken", 0, 0)


def run(fake, monkeypatch, **overrides):
    monkeypatch.setattr(anthropic, "Anthropic", lambda: fake)
    options = dict(goal=loop.GOALS["pytest"], fresh=True, stop_after=None, compact_at=None, check=True,
                   actor_model="fake", gate_on=True, lessons_path=None)
    options.update(overrides)
    loop.main(**options)
    return load_spine()


@pytest.fixture(autouse=True)
def fresh_state(repo, monkeypatch):
    apply("broken")
    monkeypatch.setattr(gate, "FIXES_PATH", repo / ".harness" / "fixes-test.md")
    (repo / ".harness" / "fixes-test.md").unlink(missing_ok=True)


def test_bare_loop_stops_on_the_oracle(monkeypatch):
    fake = FakeClient([FIX_EVERYTHING()])
    monkeypatch.setattr(loop, "review_diff", lambda *a: pytest.fail("the checker is off"))
    spine = run(fake, monkeypatch, check=False, gate_on=False)
    assert spine.status == "done" and len(fake.requests) == 1
    assert spine.passes[0].checker is None and spine.passes[0].gate is None


def test_self_assessed_goal_takes_the_models_word(monkeypatch, capsys):
    fake = FakeClient([response("end_turn", text("All better."))])
    spine = run(fake, monkeypatch, goal=loop.GOALS["self"], check=False, gate_on=False)
    assert "ACCEPTED ON THE MODEL'S WORD" in capsys.readouterr().out
    assert spine.status == "stopped"


def test_crash_and_resume_skip_finished_work(monkeypatch, capsys):
    look = response("tool_use", write_call("t0", "tax.py", green("tax.py")))
    fake = FakeClient([look, FIX_EVERYTHING()])
    spine = run(fake, monkeypatch, check=False, gate_on=False, stop_after=1)
    assert spine.status == "running" and len(spine.passes) == 1
    spine = run(fake, monkeypatch, check=False, gate_on=False, fresh=False)
    assert spine.status == "done" and [p.pass_number for p in spine.passes] == [1, 2]
    assert "Progress so far" in fake.requests[1]["messages"][0]["content"]
    run(FakeClient([]), monkeypatch, check=False, gate_on=False, fresh=False)
    assert "ALREADY DONE" in capsys.readouterr().out


def test_checker_rejection_goes_back_to_the_actor(monkeypatch):
    verdicts = iter([
        checker.Verdict(False, [checker.Violation("checkout/discounts.py", "expiry removed",
                                                  "expired codes must always be rejected", "x")], "fail", 0, 0),
        PASS_VERDICT,
    ])
    monkeypatch.setattr(loop, "review_diff", lambda *a: next(verdicts))
    fake = FakeClient([FIX_EVERYTHING(), response("end_turn", text("Kept the expiry check."))])
    spine = run(fake, monkeypatch, gate_on=False)
    assert spine.status == "done" and spine.passes[0].checker == "fail"
    rejection = fake.requests[1]["messages"][-1]["content"]
    assert "expired codes must always be rejected" in rejection


def test_full_harness_gate_rejects_then_accepts(repo, monkeypatch):
    monkeypatch.setattr(loop, "review_diff", lambda *a: PASS_VERDICT)
    human = scripted_human([
        "Half-up rounding so a half paisa is charged, never dropped.",
        "reject: justify this with the INTENT.md rule about COD orders",
        "GST is charged on the amount after the discount, per invoice rules.",
        "Minimum spend is inclusive, so exactly the minimum now qualifies.",
        "Codes follow the day the order was placed, never when COD settles.",  # only the rejected block returns
    ])
    monkeypatch.setattr(loop, "ask_human", lambda items: gate.ask_human(items, read=human))
    lessons = repo / ".harness" / "lessons-test.md"
    lessons.write_text("- Check docstrings before calling a fix done.\n")
    fake = FakeClient([FIX_EVERYTHING(), response("end_turn", text("Justified from INTENT.md."))])
    spine = run(fake, monkeypatch, lessons_path=lessons)
    assert spine.status == "done"
    assert (spine.passes[0].checker, spine.passes[0].gate) == ("pass", "fail")
    assert "Check docstrings" in fake.requests[0]["system"]
    assert "COD orders" in fake.requests[1]["messages"][-1]["content"]
    with pytest.raises(StopIteration):
        human("")


def test_no_human_means_no_acceptance(monkeypatch, capsys):
    monkeypatch.setattr(loop, "review_diff", lambda *a: PASS_VERDICT)
    monkeypatch.setattr("sys.stdin", type("NoTTY", (), {"isatty": staticmethod(lambda: False)}))
    spine = run(FakeClient([FIX_EVERYTHING()]), monkeypatch)
    assert spine.status == "stopped" and "REVIEW UNAVAILABLE" in capsys.readouterr().out


def test_compaction_restarts_from_the_spine(monkeypatch, capsys):
    look = response("tool_use", write_call("t0", "tax.py", green("tax.py")))
    look.usage.input_tokens = 9_999
    fake = FakeClient([look, FIX_EVERYTHING()])
    spine = run(fake, monkeypatch, check=False, gate_on=False, compact_at=5_000)
    assert spine.passes[0].compacted and "COMPACTED" in capsys.readouterr().out
    assert len(fake.requests[1]["messages"]) == 1, "the second call starts from a one-message briefing"


# ---------------------------------------------------------------- stage 8: the outer loop

PROPOSALS = {"summary": "rounding rules were missing", "proposals": [
    {"kind": "intent_rule", "text": "Money is rounded half-up to the paisa, once, on the final amounts.",
     "evidence": "train-bugset01: money is rounded once at the end", "why_it_generalises": "every amount"},
    {"kind": "lesson", "text": "Before finishing, check what each changed function's docstring promises.",
     "evidence": "train-bugset02", "why_it_generalises": "any function"},
    {"kind": "intent_rule", "text": "In round_money use ROUND_HALF_UP.",
     "evidence": "train-bugset01", "why_it_generalises": "it doesn't"},
]}


def test_reflector_learns_only_from_training_and_only_what_you_accept(repo, monkeypatch):
    runs = repo / "runs" / "stage8"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "train-bugset01.md").write_text("DONE: goal verified on pass 2\n")
    (runs / "train-bugset01.audit").write_text("AUDIT: 1 incident(s)\n  incident  money is rounded once at the end\n")
    (runs / "before-bugset04.md").write_text("HELD-OUT SECRET")
    fake = FakeClient([response("end_turn", text(json.dumps(PROPOSALS)))])
    monkeypatch.setattr(anthropic, "Anthropic", lambda: fake)
    committed_intent = (repo / "INTENT.md").read_text()

    reflect.propose()
    sent = fake.requests[0]["messages"][0]["content"]
    assert "money is rounded once at the end" in sent and "HELD-OUT SECRET" not in sent

    human = scripted_human(["Rounding once at the end is how the invoice is reconciled.",
                            "Docstrings state contracts the tests do not check.",
                            "reject: names code, will not transfer"])
    monkeypatch.setattr(reflect, "ask_human", lambda items: gate.ask_human(items, read=human))
    reflect.gate()
    learned = (runs / "learned" / "INTENT.md").read_text()
    assert learned.startswith(committed_intent.rstrip("\n"))
    assert "rounded half-up to the paisa" in learned and "ROUND_HALF_UP" not in learned
    assert "docstring" in (runs / "learned" / "LESSONS.md").read_text()
    assert (repo / "INTENT.md").read_text() == committed_intent, "the committed intent is never edited"
    assert "--intent" in experiment.loop_command("after") and "--lessons" in experiment.loop_command("after")
    assert "--intent" not in experiment.loop_command("before")


def test_experiment_summary_counts_incidents(repo):
    runs = repo / "runs" / "stage8"
    runs.mkdir(parents=True, exist_ok=True)
    for phase, incidents in (("before", 2), ("after", 0)):
        (runs / f"{phase}-bugset04.md").write_text(
            "--- pass 1/8\nCHECKER REJECTED: x\n--- pass 2/8\nDONE: ok\ntotal tokens: input=10 output=2\n")
        (runs / f"{phase}-bugset04.audit").write_text("".join(f"  incident  rule {n}\n" for n in range(incidents)))
    table = experiment.summary()
    assert "| before | bugset04 | accepted | 2 | 0 / 1 | 10 / 2 | ? | 2: rule 0; rule 1 |" in table
    assert "| after | bugset04 | accepted | 2 | 0 / 1 | 10 / 2 | ? | 0: clean |" in table
