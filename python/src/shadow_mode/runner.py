# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""ShadowRunner — execute an agent without side effects and capture its output.

The runner is the entry point for shadow mode. It wraps the shadow agent
function, installs side-effect interception via the adapter context manager,
executes the agent on the given input, and returns a ``ShadowDecision``.

No real external calls (HTTP, DB writes, queue publishes) must escape from
inside ``shadow_execute()``. Adapter implementors are responsible for ensuring
this guarantee within their ``intercept_side_effects()`` context manager.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from .adapters.base import ShadowAdapter
from .adapters.generic import GenericAdapter
from .types import ShadowDecision


# Callable that accepts a dict and returns a dict, synchronously or asynchronously.
AgentFn = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


class ShadowRunner:
    """Executes a shadow agent without side effects.

    Wraps an agent callable and runs it inside the adapter's
    ``intercept_side_effects()`` context manager. The result is captured as a
    ``ShadowDecision`` with a stable ``decision_id`` and an ``input_hash``
    instead of the raw input (to avoid storing sensitive data).

    Args:
        agent_fn: The shadow agent coroutine. Must accept ``dict[str, Any]``
            and return ``dict[str, Any]``.
        adapter: The ``ShadowAdapter`` to use for side-effect interception.
            Defaults to ``GenericAdapter`` if not provided.

    Example::

        async def my_shadow_agent(input_data: dict) -> dict:
            return {"action": "approve", "confidence": 0.92}

        runner = ShadowRunner(agent_fn=my_shadow_agent)
        decision = await runner.shadow_execute({"amount": 500})
        print(decision.output)          # {"action": "approve", "confidence": 0.92}
        print(decision.adapter_name)    # "generic"
    """

    def __init__(
        self,
        agent_fn: AgentFn,
        adapter: ShadowAdapter | None = None,
    ) -> None:
        self._agent_fn = agent_fn
        self._adapter = adapter if adapter is not None else GenericAdapter()

    async def shadow_execute(
        self,
        input_data: dict[str, Any],
        decision_id: str | None = None,
    ) -> ShadowDecision:
        """Execute the shadow agent without side effects.

        Runs the agent function inside the adapter's interception context,
        captures its output, and returns a ``ShadowDecision``. The raw
        ``input_data`` is never stored — only a SHA-256 hash is recorded.

        Args:
            input_data: The input dict passed to both production and shadow agents.
            decision_id: Optional explicit ID to correlate with the matching
                ``ActualDecision``. If omitted, a new UUID4 is generated.

        Returns:
            ``ShadowDecision`` with output, timestamp, adapter name, and metadata.

        Raises:
            ShadowExecutionError: If the shadow agent raises an exception.

        Example::

            decision = await runner.shadow_execute(
                {"query": "approve purchase", "amount": 250},
                decision_id="order-789",
            )
        """
        resolved_id = decision_id or str(uuid.uuid4())
        input_hash = _hash_input(input_data)

        output: dict[str, Any] = {}
        execution_error: Exception | None = None

        async with self._adapter.intercept_side_effects():
            try:
                output = await self._agent_fn(input_data)
            except Exception as exc:
                execution_error = exc

        if execution_error is not None:
            raise ShadowExecutionError(
                f"Shadow agent raised an exception: {execution_error}"
            ) from execution_error

        metadata = self._adapter.get_captured_metadata()

        return ShadowDecision(
            decision_id=resolved_id,
            input_hash=input_hash,
            output=output,
            timestamp=datetime.now(timezone.utc),
            adapter_name=self._adapter.name,
            metadata=metadata,
        )

    @property
    def adapter(self) -> ShadowAdapter:
        """The adapter used for side-effect interception."""
        return self._adapter


class ShadowExecutionError(RuntimeError):
    """Raised when the shadow agent function raises an exception during execution.

    Wraps the original exception to distinguish shadow-mode failures from
    caller-side errors.
    """


def _hash_input(input_data: dict[str, Any]) -> str:
    """Compute a stable SHA-256 hex digest of a JSON-serialised input dict.

    Args:
        input_data: The agent input dict.

    Returns:
        64-character hex string of the SHA-256 digest.
    """
    serialised = json.dumps(input_data, sort_keys=True, default=str)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()
