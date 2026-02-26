# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""CrewAIAdapter — intercepts CrewAI task execution during shadow mode.

This adapter patches the CrewAI ``Task.execute_sync`` and ``Crew.kickoff``
entry points to prevent real task execution and tool usage during shadow runs.
All task invocations are recorded in the call log.

Requires: ``pip install agent-shadow-mode[crewai]``

Design notes:
- CrewAI tasks that call external tools will have those tool calls suppressed.
- The shadow agent receives stub outputs for every task execution.
- Interpret shadow outputs with awareness that tools returned stubs — the
  shadow agent's final decision reflects its routing logic, not real tool data.
- If ``crewai`` is not installed, the adapter operates in no-op mode and
  logs a warning. Shadow execution still proceeds; only interception is skipped.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

from .base import ShadowAdapter


_logger = logging.getLogger(__name__)

_STUB_TASK_OUTPUT = "__shadow_task_intercepted__"


class CrewAIAdapter(ShadowAdapter):
    """Shadow adapter for CrewAI agents.

    Intercepts ``Task.execute_sync`` and ``Crew.kickoff`` to prevent real
    task execution during shadow mode. All intercepted task executions are
    logged and returned as stub outputs.

    Example::

        from shadow_mode.adapters import CrewAIAdapter
        from shadow_mode import ShadowRunner

        adapter = CrewAIAdapter()
        runner = ShadowRunner(agent_fn=run_my_crew, adapter=adapter)
        decision = await runner.shadow_execute({"topic": "quarterly report"})
        print(decision.metadata["intercepted_tasks"])

    Args:
        stub_output: Value returned to the shadow crew for every task execution.
            Defaults to ``"__shadow_task_intercepted__"``.
    """

    def __init__(self, stub_output: str = _STUB_TASK_OUTPUT) -> None:
        self._stub_output = stub_output
        self._intercepted_tasks: list[dict[str, Any]] = []
        self._patches: list[tuple[Any, str, Any]] = []

    @property
    def name(self) -> str:
        return "crewai"

    async def _enter_interception(self) -> None:
        """Patch CrewAI Task and Crew execution methods."""
        self._intercepted_tasks = []

        stub_output = self._stub_output

        try:
            from crewai import Task  # type: ignore[import-untyped]

            original_execute_sync = Task.execute_sync

            def patched_execute_sync(self_task: Any, *args: Any, **kwargs: Any) -> Any:
                task_description = getattr(self_task, "description", "unknown_task")
                self._intercepted_tasks.append(
                    {
                        "task": task_description,
                        "args": args,
                        "kwargs": kwargs,
                    }
                )
                # Return a minimal stub that CrewAI can handle downstream.
                # We use a simple string — CrewAI tasks can return str outputs.
                return stub_output

            Task.execute_sync = patched_execute_sync  # type: ignore[method-assign]
            self._patches.append((Task, "execute_sync", original_execute_sync))

        except ImportError:
            warnings.warn(
                "crewai package not installed. CrewAIAdapter running in no-op mode. "
                "Shadow execution will proceed without task interception. "
                "Install with: pip install agent-shadow-mode[crewai]",
                stacklevel=3,
            )

        try:
            from crewai import Crew  # type: ignore[import-untyped]

            original_kickoff = Crew.kickoff

            def patched_kickoff(self_crew: Any, *args: Any, **kwargs: Any) -> Any:
                crew_name = getattr(self_crew, "name", "unknown_crew")
                self._intercepted_tasks.append(
                    {
                        "crew": crew_name,
                        "event": "kickoff_intercepted",
                        "args": args,
                        "kwargs": kwargs,
                    }
                )
                return stub_output

            Crew.kickoff = patched_kickoff  # type: ignore[method-assign]
            self._patches.append((Crew, "kickoff", original_kickoff))

        except ImportError:
            pass  # Already warned above if crewai is missing.

    async def _exit_interception(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Restore original CrewAI methods."""
        for target_class, attr_name, original in self._patches:
            setattr(target_class, attr_name, original)
        self._patches = []

    def get_captured_metadata(self) -> dict[str, Any]:
        """Return metadata about intercepted task executions.

        Returns:
            Dict with ``"intercepted_tasks"`` and ``"total_tasks"`` keys.
        """
        return {
            "intercepted_tasks": list(self._intercepted_tasks),
            "total_tasks": len(self._intercepted_tasks),
        }
