"""Testing the tester: does the checker still judge known diffs the way it should?

    python -m harness.checker_eval --trials 3

The checker is an LLM, so it can drift with a prompt edit or a model change,
and it can give different answers to the same diff. This runs it on fixed
cases (scenarios/cheats/expected.json: a diff, an intent file, the verdict it
should give) several times each, and reports pass^k: a case counts only if
*every* trial was right. Exit code 1 if a regression case fails, so it can
gate a change to checker.py the same way the tests gate checkout/.

Two kinds of case:
    regression  must hold: the honest fix passes, the cheats fail when a rule forbids them
    limitation  documents a known gap (no written rule -> no failure). If one starts
                "failing", the checker is failing things no rule forbids: worth a look.

A run costs a few cents (Haiku, 6 cases x trials).
"""

import argparse
import json
import sys
from dataclasses import dataclass
from typing import List

import anthropic

from harness.budget import cost
from harness.checker import CHECKER_MODEL, CheckerUnavailable, review_diff
from harness.paths import REPO_ROOT, SCENARIOS_DIR

CASES_PATH = SCENARIOS_DIR / "cheats" / "expected.json"


@dataclass(frozen=True)
class Case:
    diff: str
    intent: str
    expect: str  # "pass" or "fail"
    kind: str  # "regression" or "limitation"
    note: str = ""


@dataclass
class CaseResult:
    case: Case
    verdicts: List[str]  # "pass", "fail" or "error", one per trial

    @property
    def correct(self) -> int:
        return sum(verdict == self.case.expect for verdict in self.verdicts)

    @property
    def pass_hat_k(self) -> bool:
        """Right on every trial: the bar for something that gates real changes."""
        return self.correct == len(self.verdicts)


def load_cases() -> List[Case]:
    return [Case(**raw) for raw in json.loads(CASES_PATH.read_text())]


def run_eval(client: anthropic.Anthropic, trials: int) -> tuple:
    """Every case, `trials` times. Returns (results, dollars spent)."""
    results, spent = [], 0.0
    for case in load_cases():
        diff = (REPO_ROOT / case.diff).read_text()
        intent = (REPO_ROOT / case.intent).read_text()
        verdicts = []
        for _ in range(trials):
            try:
                verdict = review_diff(client, diff, intent)
            except CheckerUnavailable:
                verdicts.append("error")
                continue
            spent += cost(CHECKER_MODEL, verdict.input_tokens, verdict.output_tokens)
            verdicts.append("pass" if verdict.passed else "fail")
        results.append(CaseResult(case, verdicts))
    return results, spent


def report(results: List[CaseResult], spent: float) -> str:
    lines = [f"checker eval: {CHECKER_MODEL}, {len(results[0].verdicts) if results else 0} trial(s) per case", "",
             "| Diff | Intent | Expect | Verdicts | pass^k | Kind |", "|---|---|---|---|---|---|"]
    for result in results:
        case = result.case
        mark = "yes" if result.pass_hat_k else f"no ({result.correct}/{len(result.verdicts)})"
        lines.append(f"| {case.diff.split('/')[-1]} | {case.intent.split('/')[-1]} | {case.expect} | "
                     f"{' '.join(result.verdicts)} | {mark} | {case.kind} |")
    regressions = [result for result in results if result.case.kind == "regression"]
    failing = [result for result in regressions if not result.pass_hat_k]
    lines += ["", f"regression cases: {len(regressions) - len(failing)}/{len(regressions)} hold on every trial; "
                  f"cost ${spent:.4f}"]
    return "\n".join(lines)


def regressions_hold(results: List[CaseResult]) -> bool:
    return all(result.pass_hat_k for result in results if result.case.kind == "regression")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the checker on known diffs and report pass^k.")
    parser.add_argument("--trials", type=int, default=3)
    args = parser.parse_args()
    eval_results, dollars = run_eval(anthropic.Anthropic(), args.trials)
    print(report(eval_results, dollars))
    sys.exit(0 if regressions_hold(eval_results) else 1)
