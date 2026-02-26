# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""ShadowAdapter abstract base class.

All framework-specific adapters inherit from this ABC. The primary contract is
the ``intercept_side_effects()`` async context manager, which must ensure that
any external calls (HTTP requests, database writes, queue publishes, file writes)
made by the shadow agent during the context are suppressed or mocked.

Adapters must NEVER allow real side effects to escape during shadow execution.
"""

from __future__ import annotations

import abc
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator


class ShadowAdapter(abc.ABC):
    """Abstract base class for shadow mode adapters.

    A ``ShadowAdapter`` is responsible for:

    1. Intercepting and suppressing side effects during shadow agent execution.
    2. Capturing metadata about what the shadow agent *would have done*
       (e.g., which tools it called, what parameters it used).
    3. Providing a ``name`` for identification in ``ShadowDecision`` records.

    Subclasses implement ``_enter_interception()`` and ``_exit_interception()``
    to install and remove their specific mocking/patching mechanisms.

    Example::

        class MyAdapter(ShadowAdapter):
            @property
            def name(self) -> str:
                return "my_adapter"

            async def _enter_interception(self) -> None:
                # Install mocks / patches here
                ...

            async def _exit_interception(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: object,
            ) -> None:
                # Remove mocks / patches here
                ...
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable adapter name recorded in ``ShadowDecision.adapter_name``."""

    @abc.abstractmethod
    async def _enter_interception(self) -> None:
        """Install side-effect interception mechanisms (patches, mocks, hooks)."""

    @abc.abstractmethod
    async def _exit_interception(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Remove side-effect interception mechanisms.

        Called whether the shadow execution succeeded or raised an exception.
        Must not suppress exceptions unless they are framework-internal noise.
        """

    @asynccontextmanager
    async def intercept_side_effects(self) -> AsyncGenerator[None, None]:
        """Async context manager that wraps shadow agent execution.

        All code inside this context must run without real side effects.
        The context manager installs interception on entry and cleans up on exit.

        Usage::

            async with adapter.intercept_side_effects():
                result = await shadow_agent_fn(input_data)
        """
        await self._enter_interception()
        exc_type: type[BaseException] | None = None
        exc_val: BaseException | None = None
        exc_tb: object = None
        try:
            yield
        except BaseException as exc:
            exc_type = type(exc)
            exc_val = exc
            exc_tb = exc.__traceback__
            raise
        finally:
            await self._exit_interception(exc_type, exc_val, exc_tb)

    def get_captured_metadata(self) -> dict[str, Any]:
        """Return any metadata captured during the last shadow execution.

        Override in subclasses to surface framework-specific data such as
        the list of tool calls the shadow agent attempted.

        Returns:
            A dict of adapter-specific metadata. Empty dict by default.
        """
        return {}
