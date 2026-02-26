# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""LangChainAdapter — intercepts LangChain tool calls during shadow execution.

This adapter monkey-patches LangChain's ``BaseTool.arun`` and ``BaseTool.run``
methods to suppress real execution during shadow mode. All tool invocations are
captured in the call log. The actual tool code is never executed.

Requires: ``pip install agent-shadow-mode[langchain]``

Design notes:
- Patching is installed on entry and restored on exit, even if the shadow
  agent raises an exception.
- Only ``BaseTool`` is patched — custom tools that bypass the LangChain tool
  interface will not be intercepted. Verify your tool chain before using this
  adapter in production shadow runs.
- The stub response returned to the shadow agent is ``{"output": "__shadow_intercepted__"}``.
  The agent may behave differently than in production because its tools always
  return this stub — factor this into interpretation of shadow outputs.
"""

from __future__ import annotations

import functools
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from .base import ShadowAdapter


_STUB_TOOL_RESPONSE = "__shadow_intercepted__"


class LangChainAdapter(ShadowAdapter):
    """Shadow adapter for LangChain agents.

    Intercepts ``BaseTool.arun`` and ``BaseTool.run`` to prevent real tool
    execution during shadow mode. All intercepted calls are logged.

    Example::

        from shadow_mode.adapters import LangChainAdapter
        from shadow_mode import ShadowRunner

        adapter = LangChainAdapter()
        runner = ShadowRunner(agent_fn=my_langchain_agent, adapter=adapter)
        decision = await runner.shadow_execute({"query": "what is the weather?"})
        print(decision.metadata["intercepted_tool_calls"])

    Args:
        stub_response: Value returned to the shadow agent for every tool call.
            Defaults to ``"__shadow_intercepted__"``.
    """

    def __init__(self, stub_response: str = _STUB_TOOL_RESPONSE) -> None:
        self._stub_response = stub_response
        self._intercepted_calls: list[dict[str, Any]] = []
        self._patches: list[Any] = []

    @property
    def name(self) -> str:
        return "langchain"

    async def _enter_interception(self) -> None:
        """Patch LangChain BaseTool.arun and BaseTool.run."""
        self._intercepted_calls = []

        stub = self._stub_response

        def _make_sync_stub(tool_name: str) -> Any:
            def _stub(*args: Any, **kwargs: Any) -> str:
                self._intercepted_calls.append(
                    {"tool": tool_name, "args": args, "kwargs": kwargs, "mode": "sync"}
                )
                return stub

            return _stub

        def _make_async_stub(tool_name: str) -> Any:
            async def _stub(*args: Any, **kwargs: Any) -> str:
                self._intercepted_calls.append(
                    {"tool": tool_name, "args": args, "kwargs": kwargs, "mode": "async"}
                )
                return stub

            return _stub

        try:
            from langchain_core.tools import BaseTool  # type: ignore[import-untyped]

            # Capture the originals so we can restore them
            original_run = BaseTool.run
            original_arun = BaseTool.arun

            def patched_run(self_tool: Any, *args: Any, **kwargs: Any) -> str:  # type: ignore[misc]
                self._intercepted_calls.append(
                    {
                        "tool": getattr(self_tool, "name", "unknown"),
                        "args": args,
                        "kwargs": kwargs,
                        "mode": "sync",
                    }
                )
                return stub  # type: ignore[return-value]

            async def patched_arun(self_tool: Any, *args: Any, **kwargs: Any) -> str:  # type: ignore[misc]
                self._intercepted_calls.append(
                    {
                        "tool": getattr(self_tool, "name", "unknown"),
                        "args": args,
                        "kwargs": kwargs,
                        "mode": "async",
                    }
                )
                return stub  # type: ignore[return-value]

            BaseTool.run = patched_run  # type: ignore[method-assign]
            BaseTool.arun = patched_arun  # type: ignore[method-assign]

            self._patches = [(BaseTool, "run", original_run), (BaseTool, "arun", original_arun)]

        except ImportError:
            # langchain-core not installed — adapter operates in no-op mode.
            # ShadowRunner will still execute the function, but no interception occurs.
            self._patches = []

    async def _exit_interception(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Restore original LangChain BaseTool methods."""
        for target_class, attr_name, original in self._patches:
            setattr(target_class, attr_name, original)
        self._patches = []

    def get_captured_metadata(self) -> dict[str, Any]:
        """Return metadata about intercepted tool calls.

        Returns:
            Dict with ``"intercepted_tool_calls"`` and ``"total_tool_calls"`` keys.
        """
        return {
            "intercepted_tool_calls": list(self._intercepted_calls),
            "total_tool_calls": len(self._intercepted_calls),
        }
