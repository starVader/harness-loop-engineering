"""The production audit: which business rules did the accepted code break?

    venv/bin/python stage8/audit.py

Runs stage8/audit/ against the current checkout/ and prints one incident per
broken rule. Only the incident names leave this script: no test code, no
expected values. That is all the reflector ever learns about a training run,
the same way a support ticket says "invoice off by a paisa", not which line.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_CMD = [sys.executable, "-m", "pytest", "-q", "--tb=no", "-rf", "-p", "no:cacheprovider", "stage8/audit/"]


def broken_rules() -> list:
    completed = subprocess.run(AUDIT_CMD, cwd=REPO_ROOT, capture_output=True, text=True)
    return re.findall(r"^FAILED \S+::test_(\w+)", completed.stdout, flags=re.MULTILINE)


if __name__ == "__main__":
    incidents = broken_rules()
    if not incidents:
        print("AUDIT: clean, no business rule broken")
    else:
        print(f"AUDIT: {len(incidents)} incident(s)")
        for rule in incidents:
            print(f"  incident  {rule.replace('_', ' ')}")
