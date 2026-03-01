# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation
"""Shared fixtures for agent-shadow-mode tests."""

from __future__ import annotations

import pytest

from shadow_mode.types import ActualDecision, ShadowDecision


@pytest.fixture
def identical_pair() -> tuple[ShadowDecision, ActualDecision]:
    """A shadow/actual pair with identical outputs — zero deviation expected."""
    output = {"action": "approve", "confidence": 0.95}
    shadow = ShadowDecision(
        decision_id="decision-001",
        input_hash="abc123",
        output=output,
    )
    actual = ActualDecision(
        decision_id="decision-001",
        output=output,
    )
    return shadow, actual


@pytest.fixture
def divergent_pair() -> tuple[ShadowDecision, ActualDecision]:
    """A shadow/actual pair with different action values — deviation expected."""
    shadow = ShadowDecision(
        decision_id="decision-002",
        input_hash="def456",
        output={"action": "approve", "confidence": 0.9},
    )
    actual = ActualDecision(
        decision_id="decision-002",
        output={"action": "deny", "confidence": 0.6},
    )
    return shadow, actual
