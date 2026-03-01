# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""
Shadow run replay capability.

Store shadow run inputs and outputs so that historical runs can be replayed
on demand. Useful for:

- Debugging divergent decisions post-hoc
- Testing new agent versions against historical inputs
- Auditing specific decision IDs

Privacy note: Raw input data IS stored in replay records. Callers must ensure
that replay storage is access-controlled and that sensitive input data is
either sanitized before calling ``save_run`` or not stored at all.

Example
-------
>>> replay = ShadowReplay()
>>> run_id = replay.save_run(input_data={"amount": 500}, shadow_output={"action": "approve"})
>>> record = replay.get_run(run_id)
>>> record.input_data
{'amount': 500}
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["ShadowRun", "ShadowReplay"]


@dataclass
class ShadowRun:
    """A stored shadow run record for replay.

    Attributes:
        run_id:        Unique identifier for this run (auto-generated if not provided).
        input_data:    The exact input passed to the shadow agent.
        shadow_output: The output the shadow agent produced.
        actual_output: The production agent's output (if available).
        decision_id:   The decision_id from the ``ShadowDecision``, if correlated.
        adapter_name:  Adapter that was used during the run.
        saved_at:      UTC timestamp when this run was saved.
        metadata:      Optional extra data (e.g. model version, experiment tag).
    """

    input_data: dict[str, Any]
    shadow_output: dict[str, Any]
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    actual_output: dict[str, Any] | None = None
    decision_id: str | None = None
    adapter_name: str = "generic"
    saved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize this run record to a JSON string."""
        data = {
            "run_id": self.run_id,
            "input_data": self.input_data,
            "shadow_output": self.shadow_output,
            "actual_output": self.actual_output,
            "decision_id": self.decision_id,
            "adapter_name": self.adapter_name,
            "saved_at": self.saved_at.isoformat(),
            "metadata": self.metadata,
        }
        return json.dumps(data, indent=2, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "ShadowRun":
        """Deserialize a ``ShadowRun`` from its JSON representation.

        Parameters
        ----------
        json_str:
            A JSON string previously produced by ``to_json()``.

        Returns
        -------
        ShadowRun:
            The deserialized run record.
        """
        data = json.loads(json_str)
        return cls(
            run_id=data["run_id"],
            input_data=data["input_data"],
            shadow_output=data["shadow_output"],
            actual_output=data.get("actual_output"),
            decision_id=data.get("decision_id"),
            adapter_name=data.get("adapter_name", "generic"),
            saved_at=datetime.fromisoformat(data["saved_at"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ShadowReplay:
    """Storage and retrieval of shadow runs for replay.

    Supports two backends:
    - In-memory (default): fast, ephemeral, lost on process restart.
    - File-based: persistent JSONL (one JSON object per line) stored at a
      caller-specified path.

    Callers choose the backend at construction time. Both backends expose the
    same interface.

    Parameters
    ----------
    storage_path:
        If provided, runs are persisted to this JSONL file. Each ``save_run``
        call appends a line. ``load_all`` reads the full file. Set to ``None``
        (default) for in-memory-only storage.

    Example
    -------
    >>> replay = ShadowReplay(storage_path="/tmp/shadow_runs.jsonl")
    >>> run_id = replay.save_run(
    ...     input_data={"query": "approve"},
    ...     shadow_output={"decision": "allow"},
    ... )
    >>> record = replay.get_run(run_id)
    """

    storage_path: Path | str | None = None

    def __post_init__(self) -> None:
        self._in_memory: dict[str, ShadowRun] = {}
        if self.storage_path is not None:
            self.storage_path = Path(self.storage_path)
            # Load existing records from file if it exists
            self._load_from_file()

    def save_run(
        self,
        input_data: dict[str, Any],
        shadow_output: dict[str, Any],
        run_id: str | None = None,
        actual_output: dict[str, Any] | None = None,
        decision_id: str | None = None,
        adapter_name: str = "generic",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Save a shadow run and return its run ID.

        Parameters
        ----------
        input_data:
            The input data that was passed to the shadow agent.
        shadow_output:
            The output the shadow agent returned.
        run_id:
            Optional explicit run ID. A UUID4 is generated if not provided.
        actual_output:
            The production agent's output, if available.
        decision_id:
            The correlated decision ID from ``ShadowDecision``.
        adapter_name:
            The adapter used during the run.
        metadata:
            Optional extra metadata.

        Returns
        -------
        str:
            The run ID of the saved record.
        """
        run = ShadowRun(
            run_id=run_id or str(uuid.uuid4()),
            input_data=input_data,
            shadow_output=shadow_output,
            actual_output=actual_output,
            decision_id=decision_id,
            adapter_name=adapter_name,
            metadata=metadata or {},
        )
        self._in_memory[run.run_id] = run

        if self.storage_path is not None:
            self._append_to_file(run)

        return run.run_id

    def get_run(self, run_id: str) -> ShadowRun | None:
        """Retrieve a shadow run record by its ID.

        Parameters
        ----------
        run_id:
            The run ID to look up.

        Returns
        -------
        ShadowRun | None:
            The run record, or ``None`` if not found.
        """
        return self._in_memory.get(run_id)

    def replay(self, run_id: str) -> dict[str, Any] | None:
        """Retrieve the stored shadow output for a run (simulated replay).

        For a full re-execution replay (running the agent again with the same
        input), callers should retrieve the run via ``get_run`` and pass
        ``run.input_data`` to a fresh ``ShadowRunner.shadow_execute()`` call.

        Parameters
        ----------
        run_id:
            The run ID to replay.

        Returns
        -------
        dict[str, Any] | None:
            The stored shadow output, or ``None`` if the run is not found.
        """
        run = self._in_memory.get(run_id)
        return run.shadow_output if run is not None else None

    def list_runs(self) -> list[str]:
        """Return a list of all stored run IDs."""
        return list(self._in_memory.keys())

    def load_all(self) -> list[ShadowRun]:
        """Return all stored run records."""
        return list(self._in_memory.values())

    # ------------------------------------------------------------------
    # File I/O helpers
    # ------------------------------------------------------------------

    def _append_to_file(self, run: ShadowRun) -> None:
        """Append a single run as a JSON line to the storage file."""
        assert self.storage_path is not None
        with open(self.storage_path, "a", encoding="utf-8") as file_handle:
            file_handle.write(run.to_json().replace("\n", " ") + "\n")

    def _load_from_file(self) -> None:
        """Load all runs from the storage JSONL file into memory."""
        assert self.storage_path is not None
        if not Path(self.storage_path).exists():
            return
        with open(self.storage_path, encoding="utf-8") as file_handle:
            for line in file_handle:
                line = line.strip()
                if line:
                    try:
                        run = ShadowRun.from_json(line)
                        self._in_memory[run.run_id] = run
                    except (json.JSONDecodeError, KeyError):
                        pass  # Skip malformed lines
