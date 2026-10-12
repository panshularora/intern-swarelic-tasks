"""Rules engine: conditions, actions, first-match-wins evaluation."""
from dataclasses import dataclass, field
from typing import Any


VALID_OPERATORS = frozenset([
    'eq', 'ne', 'gt', 'gte', 'lt', 'lte',
    'in', 'not_in', 'contains', 'startswith'
])

VALID_ACTION_TYPES = frozenset([
    'route', 'voicemail', 'escalate', 'hangup', 'play_message'
])


def _safe_compare(op, actual, value):
    try:
        return op(actual, value)
    except TypeError:
        return False


@dataclass
class Condition:
    field: str
    operator: str
    value: Any

    def evaluate(self, context: dict) -> bool:
        """
        Evaluate this condition against the given context dict.

        Returns False if the field is not in context.
        Raises ValueError for unknown operators.
        """
        if self.operator not in VALID_OPERATORS:
            raise ValueError(
                f"Unknown operator '{self.operator}'. "
                f"Valid operators: {sorted(VALID_OPERATORS)}"
            )

        if self.field not in context:
            return False

        actual = context[self.field]
        op = self.operator

        if op == 'eq':
            return actual == self.value
        if op == 'ne':
            return actual != self.value
        if op == 'gt':
            return _safe_compare(lambda a, v: a > v, actual, self.value)
        if op == 'gte':
            return _safe_compare(lambda a, v: a >= v, actual, self.value)
        if op == 'lt':
            return _safe_compare(lambda a, v: a < v, actual, self.value)
        if op == 'lte':
            return _safe_compare(lambda a, v: a <= v, actual, self.value)
        if op == 'in':
            try:
                return actual in self.value
            except TypeError:
                return False
        if op == 'not_in':
            try:
                return actual not in self.value
            except TypeError:
                return False
        if op == 'contains':
            try:
                return self.value in actual
            except TypeError:
                return False
        if op == 'startswith':
            return str(actual).startswith(str(self.value))

        raise ValueError(
            f"Unknown operator '{self.operator}'. "
            f"Valid operators: {sorted(VALID_OPERATORS)}"
        )


@dataclass
class Action:
    type: str
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.type not in VALID_ACTION_TYPES:
            raise ValueError(
                f"Invalid action type '{self.type}'. "
                f"Valid types: {sorted(VALID_ACTION_TYPES)}"
            )


@dataclass
class Rule:
    id: str
    name: str
    priority: int
    conditions: list[Condition]
    action: Action

    def matches(self, context: dict) -> bool:
        """True only when every condition passes. Empty list always matches."""
        return all(cond.evaluate(context) for cond in self.conditions)


class RulesEngine:
    def __init__(self, rules: list[Rule]):
        self.rules = sorted(rules, key=lambda r: r.priority)

    def evaluate(self, context: dict) -> 'Action | None':
        """Return the action of the first matching rule, else None."""
        for rule in self.rules:
            if rule.matches(context):
                return rule.action
        return None

    def evaluate_all(self, context: dict) -> 'list[tuple[Rule, Action]]':
        """Return every matching rule as (Rule, Action)."""
        return [(rule, rule.action) for rule in self.rules if rule.matches(context)]
