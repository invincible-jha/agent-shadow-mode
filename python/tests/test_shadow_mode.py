# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation
"""
Tests for agent-shadow-mode — types, comparator, runner, and scoring.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from shadow_mode.comparator import ShadowComparator
from shadow_mode.runner import ShadowExecutionError, ShadowRunner, _hash_input
from shadow_mode.types import (
    ActualDecision,
    AgreementLevel,
    ComparisonResult,
    ConfidenceReport,
    Deviation,
    RiskLevel,
    ShadowDecision,
)


# ---------------------------------------------------------------------------
# TestShadowDecision
# ---------------------------------------------------------------------------


class TestShadowDecision:
    def test_valid_construction(self) -> None:
        decision = ShadowDecision(
            decision_id="test-id",
            input_hash="abc",
            output={"action": "approve"},
        )
        assert decision.decision_id == "test-id"
        assert decision.output == {"action": "approve"}

    def test_timestamp_is_set_automatically(self) -> None:
        decision = ShadowDecision(
            decision_id="test-id",
            input_hash="abc",
            output={},
        )
        assert decision.timestamp is not None

    def test_adapter_name_defaults_to_generic(self) -> None:
        decision = ShadowDecision(
            decision_id="test-id",
            input_hash="abc",
            output={},
        )
        assert decision.adapter_name == "generic"

    def test_metadata_defaults_to_empty_dict(self) -> None:
        decision = ShadowDecision(
            decision_id="test-id",
            input_hash="abc",
            output={},
        )
        assert decision.metadata == {}


# ---------------------------------------------------------------------------
# TestComparisonResult
# ---------------------------------------------------------------------------


class TestComparisonResult:
    def test_valid_agreed_result(self) -> None:
        result = ComparisonResult(
            decision_id="test-id",
            agreed=True,
            agreement_level=AgreementLevel.FULL,
            deviation_score=0.0,
            risk_level=RiskLevel.LOW,
        )
        assert result.agreed is True
        assert result.deviation_score == 0.0

    def test_disagreed_with_zero_score_raises_validation_error(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ComparisonResult(
                decision_id="test-id",
                agreed=False,
                agreement_level=AgreementLevel.NONE,
                deviation_score=0.0,
                risk_level=RiskLevel.LOW,
            )

    def test_deviation_score_must_be_in_range(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ComparisonResult(
                decision_id="test-id",
                agreed=False,
                agreement_level=AgreementLevel.NONE,
                deviation_score=1.5,  # > 1.0
                risk_level=RiskLevel.HIGH,
            )


# ---------------------------------------------------------------------------
# TestShadowComparator
# ---------------------------------------------------------------------------


class TestShadowComparator:
    def test_identical_outputs_produce_zero_deviation(
        self, identical_pair: tuple[ShadowDecision, ActualDecision]
    ) -> None:
        shadow, actual = identical_pair
        comparator = ShadowComparator()
        result = comparator.compare(shadow, actual)
        assert result.deviation_score == 0.0
        assert result.agreed is True
        assert result.agreement_level == AgreementLevel.FULL

    def test_different_action_field_produces_high_risk(
        self, divergent_pair: tuple[ShadowDecision, ActualDecision]
    ) -> None:
        shadow, actual = divergent_pair
        comparator = ShadowComparator()
        result = comparator.compare(shadow, actual)
        assert result.agreed is False
        assert result.risk_level == RiskLevel.HIGH

    def test_mismatched_decision_ids_raise_value_error(self) -> None:
        shadow = ShadowDecision(
            decision_id="id-A",
            input_hash="hash-a",
            output={"action": "approve"},
        )
        actual = ActualDecision(
            decision_id="id-B",
            output={"action": "approve"},
        )
        comparator = ShadowComparator()
        with pytest.raises(ValueError, match="decision_id mismatch"):
            comparator.compare(shadow, actual)

    def test_missing_field_in_actual_produces_deviation(self) -> None:
        shadow = ShadowDecision(
            decision_id="id-1",
            input_hash="hash",
            output={"action": "approve", "extra_field": "value"},
        )
        actual = ActualDecision(
            decision_id="id-1",
            output={"action": "approve"},
        )
        comparator = ShadowComparator()
        result = comparator.compare(shadow, actual)
        field_paths = [d.field_path for d in result.deviations]
        assert "extra_field" in field_paths

    def test_extra_field_in_actual_produces_deviation(self) -> None:
        shadow = ShadowDecision(
            decision_id="id-2",
            input_hash="hash",
            output={"action": "approve"},
        )
        actual = ActualDecision(
            decision_id="id-2",
            output={"action": "approve", "extra_field": "value"},
        )
        comparator = ShadowComparator()
        result = comparator.compare(shadow, actual)
        field_paths = [d.field_path for d in result.deviations]
        assert "extra_field" in field_paths

    def test_low_priority_field_difference_produces_medium_risk(self) -> None:
        shadow = ShadowDecision(
            decision_id="id-3",
            input_hash="hash",
            output={"some_low_priority_field": "a"},
        )
        actual = ActualDecision(
            decision_id="id-3",
            output={"some_low_priority_field": "b"},
        )
        comparator = ShadowComparator()
        result = comparator.compare(shadow, actual)
        # some_low_priority_field is not in high_priority_fields → MEDIUM risk
        assert result.risk_level == RiskLevel.MEDIUM

    def test_result_decision_id_matches_input(
        self, identical_pair: tuple[ShadowDecision, ActualDecision]
    ) -> None:
        shadow, actual = identical_pair
        comparator = ShadowComparator()
        result = comparator.compare(shadow, actual)
        assert result.decision_id == shadow.decision_id

    def test_invalid_agreement_threshold_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="agreement_threshold"):
            ShadowComparator(agreement_threshold=1.5)

    def test_nested_output_deviation_uses_dot_path(self) -> None:
        shadow = ShadowDecision(
            decision_id="id-nested",
            input_hash="hash",
            output={"details": {"score": 0.9}},
        )
        actual = ActualDecision(
            decision_id="id-nested",
            output={"details": {"score": 0.5}},
        )
        comparator = ShadowComparator()
        result = comparator.compare(shadow, actual)
        field_paths = [d.field_path for d in result.deviations]
        assert "details.score" in field_paths


# ---------------------------------------------------------------------------
# TestShadowRunner
# ---------------------------------------------------------------------------


class TestShadowRunner:
    def test_shadow_execute_returns_shadow_decision(self) -> None:
        async def agent_fn(input_data: dict[str, Any]) -> dict[str, Any]:
            return {"action": "approve"}

        runner = ShadowRunner(agent_fn=agent_fn)
        decision = asyncio.get_event_loop().run_until_complete(
            runner.shadow_execute({"task": "review"})
        )
        assert isinstance(decision, ShadowDecision)
        assert decision.output == {"action": "approve"}

    def test_shadow_execute_stores_input_hash_not_raw_input(self) -> None:
        async def agent_fn(input_data: dict[str, Any]) -> dict[str, Any]:
            return {}

        runner = ShadowRunner(agent_fn=agent_fn)
        input_data = {"task": "review", "user": "alice"}
        decision = asyncio.get_event_loop().run_until_complete(
            runner.shadow_execute(input_data)
        )
        expected_hash = _hash_input(input_data)
        assert decision.input_hash == expected_hash
        # Raw input must not appear in the decision
        assert "alice" not in str(decision.model_dump())

    def test_shadow_execute_uses_provided_decision_id(self) -> None:
        async def agent_fn(input_data: dict[str, Any]) -> dict[str, Any]:
            return {}

        runner = ShadowRunner(agent_fn=agent_fn)
        decision = asyncio.get_event_loop().run_until_complete(
            runner.shadow_execute({}, decision_id="custom-id")
        )
        assert decision.decision_id == "custom-id"

    def test_shadow_execute_generates_uuid_when_no_id_provided(self) -> None:
        async def agent_fn(input_data: dict[str, Any]) -> dict[str, Any]:
            return {}

        runner = ShadowRunner(agent_fn=agent_fn)
        decision = asyncio.get_event_loop().run_until_complete(
            runner.shadow_execute({})
        )
        # UUID4 format: 8-4-4-4-12 hex chars
        assert len(decision.decision_id) == 36
        assert decision.decision_id.count("-") == 4

    def test_shadow_execute_raises_shadow_execution_error_on_agent_failure(self) -> None:
        async def failing_agent(input_data: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("Agent crashed")

        runner = ShadowRunner(agent_fn=failing_agent)
        with pytest.raises(ShadowExecutionError, match="Shadow agent raised an exception"):
            asyncio.get_event_loop().run_until_complete(runner.shadow_execute({}))

    def test_adapter_property_returns_adapter(self) -> None:
        async def agent_fn(input_data: dict[str, Any]) -> dict[str, Any]:
            return {}

        runner = ShadowRunner(agent_fn=agent_fn)
        assert runner.adapter is not None
        assert runner.adapter.name == "generic"


# ---------------------------------------------------------------------------
# TestHashInput
# ---------------------------------------------------------------------------


class TestHashInput:
    def test_same_dict_produces_same_hash(self) -> None:
        data = {"a": 1, "b": "hello"}
        assert _hash_input(data) == _hash_input(data)

    def test_different_dicts_produce_different_hashes(self) -> None:
        assert _hash_input({"a": 1}) != _hash_input({"a": 2})

    def test_hash_is_64_chars_hex(self) -> None:
        result = _hash_input({"test": "value"})
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


# ---------------------------------------------------------------------------
# TestConfidenceReport
# ---------------------------------------------------------------------------


class TestConfidenceReport:
    def test_valid_construction(self) -> None:
        report = ConfidenceReport(
            total_comparisons=10,
            agreement_count=8,
            disagreement_count=2,
            agreement_rate=0.8,
            average_deviation=0.1,
            worst_deviation=0.4,
            risk_score=0.2,
            high_risk_count=1,
            recommendation="Results look stable.",
        )
        assert report.agreement_rate == 0.8

    def test_count_mismatch_raises_validation_error(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="total_comparisons"):
            ConfidenceReport(
                total_comparisons=10,
                agreement_count=7,
                disagreement_count=2,  # 7 + 2 != 10
                agreement_rate=0.7,
                average_deviation=0.1,
                worst_deviation=0.3,
                risk_score=0.2,
                high_risk_count=0,
                recommendation="Mismatch test",
            )
