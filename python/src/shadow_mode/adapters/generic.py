# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""GenericAdapter — wraps any Python callable for shadow execution.

The GenericAdapter does not install any framework-specific patches. It relies on
callers to pass callables that are already safe to run in shadow mode (i.e., they
do not produce real side effects), or to wrap side-effectful callables with their
own suppression logic.

For simple functions that are purely computational, ``GenericAdapter`` is sufficient.
For agents that make HTTP calls, use ``LangChainAdapter`` or ``CrewAIAdapter``.
"""

from __future__ import annotations

from typing import Any

from .base import ShadowAdapter


class GenericAdapter(ShadowAdapter):
    """Minimal adapter for wrapping any Python callable.

    This adapter provides no automatic side-effect suppression. It is suitable for:

    - Pure functions that have no side effects.
    - Functions where the caller has already ensured shadow safety.
    - Testing and development scenarios.

    For production use with agents that make external calls, prefer
    ``LangChainAdapter`` or ``CrewAIAdapter``.

    Example::

        adapter = GenericAdapter()
        runner = ShadowRunner(agent_fn=my_pure_fn, adapter=adapter)
        decision = await runner.shadow_execute({"x": 42})
    """

    def __init__(self) -> None:
        self._active = False
        self._call_log: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "generic"

    async def _enter_interception(self) -> None:
        self._active = True
        self._call_log = []

    async def _exit_interception(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self._active = False

    def log_call(self, call_name: str, parameters: dict[str, Any]) -> None:
        """Manually record a side-effectful call for metadata capture.

        Callers can invoke this from within their wrapped function to surface
        call metadata in ``ShadowDecision.metadata``.

        Args:
            call_name: Descriptive name of the call (e.g. ``"http.post"``).
            parameters: Parameters that would have been passed.
        """
        if self._active:
            self._call_log.append({"call": call_name, "parameters": parameters})

    def get_captured_metadata(self) -> dict[str, Any]:
        """Return the call log accumulated during shadow execution.

        Returns:
            Dict with ``"intercepted_calls"`` key containing list of call records.
        """
        return {"intercepted_calls": list(self._call_log)}
