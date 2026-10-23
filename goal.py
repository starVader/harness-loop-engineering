"""What "done" means for a loop run, and whether code can check it.

is_met() returns:
  True   verified done: the loop stops
  False  verified not done: the loop keeps going
  None   code cannot check it: the loop runs until the model stops, then
         takes the model's word for it
"""

from typing import Dict, Optional, Protocol

from tools import run_tests


class Goal(Protocol):
    name: str
    description: str

    def is_met(self) -> Optional[bool]: ...


class PytestGoal:
    """The oracle: done means the test suite passes, checked by code."""

    name = "pytest"
    description = "Every test in tests/ passes."

    def is_met(self) -> Optional[bool]:
        return run_tests().exit_code == 0


class SelfAssessedGoal:
    """The 'be happier' goal: nothing code can measure, so only the model can say done."""

    name = "self"
    description = "Make the checkout service better."

    def is_met(self) -> Optional[bool]:
        return None


GOALS: Dict[str, Goal] = {goal.name: goal for goal in (PytestGoal(), SelfAssessedGoal())}
