"""Tests for the rules engine."""
from pathlib import Path

import pytest
from rules_engine.engine import Condition, Rule, Action, RulesEngine
from rules_engine.loader import load_rules_from_json, load_rules_from_dict


SAMPLE_RULES = Path(__file__).resolve().parent.parent / 'sample_rules.json'


@pytest.fixture
def vip_rule():
    return Rule(
        id='rule-001',
        name='VIP Bypass',
        priority=1,
        conditions=[
            Condition(field='caller_tag', operator='in', value=['VIP', 'PREMIUM'])
        ],
        action=Action(type='route', data={'target': 'vip-queue'})
    )


@pytest.fixture
def after_hours_rule():
    return Rule(
        id='rule-003',
        name='After Hours',
        priority=3,
        conditions=[
            Condition(field='hour_of_day', operator='gte', value=21)
        ],
        action=Action(type='voicemail', data={'message': 'We are closed.'})
    )


@pytest.fixture
def repeat_caller_rule():
    return Rule(
        id='rule-005',
        name='Repeat Caller',
        priority=5,
        conditions=[
            Condition(field='call_count', operator='gt', value=3)
        ],
        action=Action(type='escalate', data={'target': 'supervisor'})
    )


class TestCondition:

    def test_eq_operator_match(self):
        cond = Condition(field='status', operator='eq', value='active')
        assert cond.evaluate({'status': 'active'}) is True

    def test_eq_operator_no_match(self):
        cond = Condition(field='status', operator='eq', value='active')
        assert cond.evaluate({'status': 'inactive'}) is False

    def test_missing_field_returns_false(self):
        cond = Condition(field='nonexistent', operator='eq', value='anything')
        assert cond.evaluate({}) is False

    def test_unknown_operator_raises_value_error(self):
        cond = Condition(field='x', operator='INVALID_OP', value=1)
        with pytest.raises(ValueError, match="Unknown operator"):
            cond.evaluate({'x': 1})

    def test_gt_operator_true(self):
        cond = Condition(field='call_count', operator='gt', value=3)
        assert cond.evaluate({'call_count': 4}) is True

    def test_gt_operator_false(self):
        cond = Condition(field='call_count', operator='gt', value=3)
        assert cond.evaluate({'call_count': 3}) is False

    def test_in_operator_match(self):
        cond = Condition(field='tag', operator='in', value=['VIP', 'PREMIUM'])
        assert cond.evaluate({'tag': 'VIP'}) is True

    def test_in_operator_no_match(self):
        cond = Condition(field='tag', operator='in', value=['VIP', 'PREMIUM'])
        assert cond.evaluate({'tag': 'STANDARD'}) is False

    def test_not_in_operator(self):
        cond = Condition(field='tag', operator='not_in', value=['BLOCKED'])
        assert cond.evaluate({'tag': 'VIP'}) is True
        assert cond.evaluate({'tag': 'BLOCKED'}) is False

    def test_contains_operator(self):
        cond = Condition(field='notes', operator='contains', value='urgent')
        assert cond.evaluate({'notes': 'This is an urgent matter'}) is True
        assert cond.evaluate({'notes': 'Normal inquiry'}) is False

    def test_contains_operator_on_list(self):
        cond = Condition(field='skills', operator='contains', value='billing')
        assert cond.evaluate({'skills': ['sales', 'billing']}) is True
        assert cond.evaluate({'skills': ['sales']}) is False

    def test_gte_and_lte(self):
        gte = Condition(field='hour_of_day', operator='gte', value=21)
        lte = Condition(field='hour_of_day', operator='lte', value=8)
        assert gte.evaluate({'hour_of_day': 21}) is True
        assert gte.evaluate({'hour_of_day': 20}) is False
        assert lte.evaluate({'hour_of_day': 8}) is True
        assert lte.evaluate({'hour_of_day': 9}) is False

    def test_lt_and_ne(self):
        lt = Condition(field='hour_of_day', operator='lt', value=9)
        ne = Condition(field='caller_tag', operator='ne', value='BLOCKED')
        assert lt.evaluate({'hour_of_day': 8}) is True
        assert lt.evaluate({'hour_of_day': 9}) is False
        assert ne.evaluate({'caller_tag': 'VIP'}) is True
        assert ne.evaluate({'caller_tag': 'BLOCKED'}) is False

    def test_startswith(self):
        cond = Condition(field='caller_number', operator='startswith', value='+91')
        assert cond.evaluate({'caller_number': '+91-9876543210'}) is True
        assert cond.evaluate({'caller_number': '+1-2025550100'}) is False


class TestRule:

    def test_all_conditions_must_match(self, vip_rule):
        assert vip_rule.matches({'caller_tag': 'VIP'}) is True

    def test_any_failing_condition_returns_false(self):
        rule = Rule(
            id='r', name='test', priority=1,
            conditions=[
                Condition('a', 'eq', 1),
                Condition('b', 'eq', 2),
            ],
            action=Action(type='hangup')
        )
        assert rule.matches({'a': 1, 'b': 99}) is False

    def test_empty_conditions_always_matches(self):
        rule = Rule(
            id='r', name='catch-all', priority=99,
            conditions=[],
            action=Action(type='route', data={'target': 'default-queue'})
        )
        assert rule.matches({}) is True
        assert rule.matches({'anything': 'here'}) is True


class TestRulesEngine:

    def test_vip_bypass_scenario(self, vip_rule, after_hours_rule):
        engine = RulesEngine([after_hours_rule, vip_rule])
        action = engine.evaluate({'caller_tag': 'VIP', 'hour_of_day': 22})
        assert action is not None
        assert action.type == 'route'

    def test_no_match_returns_none(self, vip_rule):
        engine = RulesEngine([vip_rule])
        action = engine.evaluate({'caller_tag': 'STANDARD', 'hour_of_day': 14})
        assert action is None

    def test_rules_evaluated_in_priority_order(self, vip_rule, after_hours_rule, repeat_caller_rule):
        engine = RulesEngine([repeat_caller_rule, after_hours_rule, vip_rule])
        action = engine.evaluate({'caller_tag': 'VIP', 'call_count': 10, 'hour_of_day': 14})
        assert action.type == 'route'

    def test_evaluate_all_returns_all_matches(self, vip_rule, after_hours_rule):
        engine = RulesEngine([vip_rule, after_hours_rule])
        results = engine.evaluate_all({'caller_tag': 'VIP', 'hour_of_day': 22})
        assert len(results) == 2

    def test_sample_json_scenarios(self):
        engine = RulesEngine(load_rules_from_json(SAMPLE_RULES))

        vip = engine.evaluate({'caller_tag': 'VIP', 'hour_of_day': 14, 'call_count': 1})
        assert vip.type == 'route'
        assert vip.data['target'] == 'vip-queue'

        night = engine.evaluate({'caller_tag': 'STANDARD', 'hour_of_day': 22, 'call_count': 1})
        assert night.type == 'voicemail'

        repeat = engine.evaluate({'caller_tag': 'STANDARD', 'hour_of_day': 10, 'call_count': 4})
        assert repeat.type == 'escalate'

        none = engine.evaluate({'caller_tag': 'STANDARD', 'hour_of_day': 10, 'call_count': 1})
        assert none is None


class TestLoader:

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_rules_from_json(tmp_path / 'nope.json')

    def test_missing_key_raises(self):
        with pytest.raises(ValueError, match="missing key"):
            load_rules_from_dict([{'id': 'x'}])

    def test_bad_action_type_raises(self):
        with pytest.raises(ValueError, match="invalid action type"):
            load_rules_from_dict([{
                'id': 'x',
                'name': 'bad',
                'priority': 1,
                'conditions': [],
                'action': {'type': 'explode'},
            }])
