# Adapters

An adapter is responsible for suppressing all real side effects when a shadow agent
runs. It installs interception hooks before the shadow agent executes and removes
them cleanly after, even if the agent raises an exception.

---

## The ShadowAdapter contract

All adapters inherit from `ShadowAdapter` in `shadow_mode/adapters/base.py`.

```python
class ShadowAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this adapter (e.g. 'langchain')."""

    @asynccontextmanager
    async def intercept_side_effects(self) -> AsyncIterator[None]:
        """Async context manager that suppresses side effects."""
        await self._enter_interception()
        try:
            yield
        finally:
            await self._exit_interception(...)

    @abstractmethod
    async def _enter_interception(self) -> None:
        """Install interception hooks."""

    @abstractmethod
    async def _exit_interception(self, exc_type, exc_val, exc_tb) -> None:
        """Remove interception hooks."""

    @abstractmethod
    def get_captured_metadata(self) -> dict[str, Any]:
        """Return metadata about intercepted calls after execution."""
```

The context manager pattern guarantees that `_exit_interception` is always called,
preserving the integrity of the production code paths.

---

## GenericAdapter

`GenericAdapter` is the default adapter. It performs no interception — it simply
provides the context manager interface without patching anything.

Use it when:

- Your shadow agent function does not make any external calls.
- You want to confirm shadow mode works before adding framework-specific interception.
- You are running agents that have already isolated their side effects via
  dependency injection.

```python
from shadow_mode.adapters import GenericAdapter
from shadow_mode import ShadowRunner

runner = ShadowRunner(agent_fn=my_agent, adapter=GenericAdapter())
decision = await runner.shadow_execute(input_data)
```

`get_captured_metadata()` returns `{}` for `GenericAdapter`.

---

## LangChainAdapter

`LangChainAdapter` intercepts LangChain tool execution during shadow runs.

### What it patches

It monkey-patches two methods on `langchain_core.tools.BaseTool`:

| Method | Original | Shadow replacement |
|--------|----------|--------------------|
| `BaseTool.run` | Executes the tool synchronously | Returns stub string |
| `BaseTool.arun` | Executes the tool asynchronously | Returns stub string |

Both patched methods log the call to the adapter's internal call list and return
`"__shadow_intercepted__"` (or a custom stub string).

### Installation

```bash
pip install agent-shadow-mode[langchain]
# or: pip install agent-shadow-mode langchain-core
```

### Usage

```python
from shadow_mode.adapters import LangChainAdapter
from shadow_mode import ShadowRunner

adapter = LangChainAdapter()  # or: LangChainAdapter(stub_response="<stub>")
runner = ShadowRunner(agent_fn=my_langchain_agent, adapter=adapter)

decision = await runner.shadow_execute({"query": "process refund", "amount": 200})

# Inspect what tool calls the shadow agent attempted
tool_calls = decision.metadata["intercepted_tool_calls"]
total_calls = decision.metadata["total_tool_calls"]
```

### Limitations

- Only `BaseTool` subclasses are intercepted. If your agent calls external services
  via raw `httpx` / `aiohttp` / `requests` (bypassing LangChain's tool interface),
  those calls are not suppressed. Wrap such calls in a `BaseTool`.
- The stub response `"__shadow_intercepted__"` is always a string. If your tool
  returns a structured object and your agent's parsing logic fails on a string stub,
  the shadow agent may raise or produce unusual output. Set a custom `stub_response`
  that your agent can handle:

  ```python
  adapter = LangChainAdapter(stub_response='{"status": "stub"}')
  ```

- Patch state is stored on the adapter instance, so each `ShadowRunner` should use
  its own `LangChainAdapter` instance if you run multiple concurrent shadow
  evaluations.

### If langchain-core is not installed

The adapter operates in no-op mode (equivalent to `GenericAdapter`) and the shadow
execution proceeds without tool interception. No exception is raised at import time
so that `agent-shadow-mode` can be installed without requiring LangChain.

---

## CrewAIAdapter

`CrewAIAdapter` intercepts CrewAI task execution during shadow runs.

### What it patches

| Method | Original | Shadow replacement |
|--------|----------|--------------------|
| `Task.execute_sync` | Runs the task and its tools | Returns stub string |
| `Crew.kickoff` | Runs the full crew pipeline | Returns stub string |

### Installation

```bash
pip install agent-shadow-mode[crewai]
# or: pip install agent-shadow-mode crewai
```

### Usage

```python
from shadow_mode.adapters import CrewAIAdapter
from shadow_mode import ShadowRunner

async def run_my_crew(input_data: dict) -> dict:
    crew = MyCrew(inputs=input_data)
    result = crew.kickoff()
    return {"output": result}

adapter = CrewAIAdapter()
runner = ShadowRunner(agent_fn=run_my_crew, adapter=adapter)

decision = await runner.shadow_execute({"topic": "quarterly report"})

intercepted_tasks = decision.metadata["intercepted_tasks"]
total_tasks = decision.metadata["total_tasks"]
```

### Limitations

- Individual tool calls made inside `Task.execute_sync` by CrewAI agents are also
  suppressed because the task itself is stubbed before tool execution.
- If your crew's agents use custom task delegation patterns that bypass
  `Task.execute_sync`, those paths are not intercepted.
- If `crewai` is not installed, a `UserWarning` is issued and the adapter runs
  in no-op mode.

---

## Writing a custom adapter

To support a framework not covered by the built-in adapters, subclass
`ShadowAdapter`:

```python
from shadow_mode.adapters.base import ShadowAdapter
from typing import Any

class MyFrameworkAdapter(ShadowAdapter):

    def __init__(self) -> None:
        self._intercepted: list[dict[str, Any]] = []
        self._patches: list[tuple[Any, str, Any]] = []

    @property
    def name(self) -> str:
        return "my_framework"

    async def _enter_interception(self) -> None:
        self._intercepted = []
        import my_framework

        original = my_framework.Client.send

        def stub_send(self_client: Any, *args: Any, **kwargs: Any) -> str:
            self._intercepted.append({"args": args, "kwargs": kwargs})
            return "__shadow_intercepted__"

        my_framework.Client.send = stub_send  # type: ignore[method-assign]
        self._patches.append((my_framework.Client, "send", original))

    async def _exit_interception(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        for target, attr_name, original in self._patches:
            setattr(target, attr_name, original)
        self._patches.clear()

    def get_captured_metadata(self) -> dict[str, Any]:
        return {
            "intercepted_calls": list(self._intercepted),
            "total_calls": len(self._intercepted),
        }
```

Register the adapter by passing it directly to `ShadowRunner`:

```python
runner = ShadowRunner(agent_fn=my_agent, adapter=MyFrameworkAdapter())
```

### Custom adapter checklist

- Always restore originals in `_exit_interception`, even if `exc_type` is set.
- Store originals before patching, not after.
- Reset `self._intercepted` at the start of `_enter_interception` — the adapter
  instance may be reused across multiple shadow runs.
- Return a fresh copy of the intercepted list from `get_captured_metadata()` so
  that the caller cannot mutate internal state.
- Use type annotations on all method signatures.
