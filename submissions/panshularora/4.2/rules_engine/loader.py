"""Load rules from JSON / dicts into Rule objects."""
import json
from pathlib import Path
from .engine import Rule, Condition, Action, VALID_ACTION_TYPES


REQUIRED_RULE_KEYS = ('id', 'name', 'priority', 'conditions', 'action')
REQUIRED_CONDITION_KEYS = ('field', 'operator', 'value')


def load_rules_from_json(path: str | Path) -> list[Rule]:
    """
    Load rules from a JSON file.

    Raises:
        FileNotFoundError: if path doesn't exist
        ValueError: if any rule is malformed
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Rules file not found: {path}")

    with path.open('r', encoding='utf-8') as f:
        data = json.load(f)

    return load_rules_from_dict(data)


def load_rules_from_dict(data: list[dict]) -> list[Rule]:
    """Parse a list of rule dicts into Rule objects."""
    if not isinstance(data, list):
        raise ValueError("Rules data must be a JSON array")

    rules = []
    for i, raw in enumerate(data):
        rules.append(_parse_rule(i, raw))
    return rules


def _parse_rule(index: int, raw: dict) -> Rule:
    if not isinstance(raw, dict):
        raise ValueError(f"Rule {index}: expected an object")

    for key in REQUIRED_RULE_KEYS:
        if key not in raw:
            raise ValueError(f"Rule {index}: missing key '{key}'")

    priority = raw['priority']
    if not isinstance(priority, int) or isinstance(priority, bool) or priority < 1:
        raise ValueError(f"Rule {index}: priority must be a positive integer")

    conditions_raw = raw['conditions']
    if not isinstance(conditions_raw, list):
        raise ValueError(f"Rule {index}: conditions must be a list")

    conditions = []
    for j, cond in enumerate(conditions_raw):
        if not isinstance(cond, dict):
            raise ValueError(f"Rule {index}: condition {j} must be an object")
        for ck in REQUIRED_CONDITION_KEYS:
            if ck not in cond:
                raise ValueError(f"Rule {index}: condition {j} missing key '{ck}'")
        conditions.append(Condition(
            field=cond['field'],
            operator=cond['operator'],
            value=cond['value'],
        ))

    action_raw = raw['action']
    if not isinstance(action_raw, dict) or 'type' not in action_raw:
        raise ValueError(f"Rule {index}: action must include 'type'")

    action_type = action_raw['type']
    if action_type not in VALID_ACTION_TYPES:
        raise ValueError(
            f"Rule {index}: invalid action type '{action_type}'. "
            f"Valid types: {sorted(VALID_ACTION_TYPES)}"
        )

    data = {k: v for k, v in action_raw.items() if k != 'type'}
    return Rule(
        id=str(raw['id']),
        name=str(raw['name']),
        priority=priority,
        conditions=conditions,
        action=Action(type=action_type, data=data),
    )
