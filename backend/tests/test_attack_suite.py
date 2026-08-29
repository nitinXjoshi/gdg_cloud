"""Tests for the 15-case adversarial prompt injection attack suite."""

from __future__ import annotations

from app.services.attack_suite import ATTACK_CASES, build_attack_suite, suite_summary


def test_attack_suite_contains_15_cases():
    suite = build_attack_suite()
    assert len(suite) == 15
    assert len(ATTACK_CASES) == 15


def test_all_cases_have_objectives_and_levels():
    suite = build_attack_suite()
    categories = set()
    levels = set()

    for case in suite:
        assert case.id
        assert case.category
        assert case.prompt
        assert case.objective
        assert 1 <= case.level <= 6
        assert case.severity
        categories.add(case.category)
        levels.add(case.level)

    assert len(categories) == 15
    assert levels == {1, 2, 3, 4, 5, 6}


def test_suite_summary_aggregates_categories():
    summary = suite_summary()
    assert len(summary) == 15
    assert all(count == 1 for count in summary.values())
