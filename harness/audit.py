"""The production audit: which business rules did the accepted code break?

    python -m harness.audit

Runs scenarios/audit/ against the current checkout/ and prints one incident per
broken rule. Only the incident names leave this script: no test code, no
expected values. That is all the reflector ever learns about a training run,
the same way a support ticket says "invoice off by a paisa", not which line.
"""

import re

from harness.sandbox import run_pytest


def broken_rules() -> list:
    """The audit runs actor-written code too, so it goes through the same sandbox as the tests."""
    report = run_pytest("scenarios/audit/", extra=("--tb=no", "-rf")).output_tail
    return re.findall(r"^FAILED \S+::test_(\w+)", report, flags=re.MULTILINE)


if __name__ == "__main__":
    incidents = broken_rules()
    if not incidents:
        print("AUDIT: clean, no business rule broken")
    else:
        print(f"AUDIT: {len(incidents)} incident(s)")
        for rule in incidents:
            print(f"  incident  {rule.replace('_', ' ')}")
