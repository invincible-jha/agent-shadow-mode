# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""ShadowRecorder — record shadow decisions and their outcomes.

Supports two backends:

- **In-memory** (default): stores ``ShadowDecision`` objects in a list. Data
  is lost when the process exits. Suitable for short evaluation sessions.

- **JSONL file** (opt-in): appends one JSON line per decision to a file.
  Suitable for persistent shadow runs across restarts.

The recorder never stores raw input data — only the ``input_hash`` from
``ShadowDecision``. This is intentional to avoid storing sensitive user data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .types import ShadowDecision


class ShadowRecorder:
    """Records shadow decisions with optional file persistence.

    Args:
        storage_path: Optional path to a JSONL file for persistent storage.
            If ``None``, only in-memory storage is used.
        max_memory_records: Maximum number of decisions to retain in memory.
            Oldest records are evicted when the limit is reached. Set to
            ``None`` for unlimited. Defaults to 10,000.

    Example — in-memory::

        recorder = ShadowRecorder()
        recorder.record(shadow_decision)
        history = recorder.get_history()

    Example — file-backed::

        recorder = ShadowRecorder(storage_path=Path("./shadow_records.jsonl"))
        recorder.record(shadow_decision)
        # Records persist across restarts
    """

    def __init__(
        self,
        storage_path: Path | None = None,
        max_memory_records: int | None = 10_000,
    ) -> None:
        self._storage_path = storage_path
        self._max_memory_records = max_memory_records
        self._memory: list[ShadowDecision] = []

        if storage_path is not None:
            storage_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, decision: ShadowDecision) -> None:
        """Record a shadow decision.

        Appends the decision to the in-memory list and, if a storage path was
        configured, appends a JSON line to the file.

        Args:
            decision: The ``ShadowDecision`` to record.
        """
        self._memory.append(decision)

        if (
            self._max_memory_records is not None
            and len(self._memory) > self._max_memory_records
        ):
            self._memory = self._memory[-self._max_memory_records :]

        if self._storage_path is not None:
            self._append_to_file(decision)

    def get_history(self, limit: int | None = None) -> list[ShadowDecision]:
        """Return recorded shadow decisions from memory.

        Args:
            limit: Optional maximum number of most-recent decisions to return.
                If ``None``, all in-memory decisions are returned.

        Returns:
            List of ``ShadowDecision`` objects, oldest first.
        """
        if limit is None:
            return list(self._memory)
        return list(self._memory[-limit:])

    def iter_history(self) -> Iterator[ShadowDecision]:
        """Iterate over all in-memory shadow decisions, oldest first.

        Returns:
            Iterator of ``ShadowDecision`` objects.
        """
        return iter(self._memory)

    def load_from_file(self) -> list[ShadowDecision]:
        """Load all decisions from the JSONL file into memory.

        Only available when a ``storage_path`` was configured.

        Returns:
            List of ``ShadowDecision`` objects loaded from disk.

        Raises:
            RuntimeError: If no ``storage_path`` was configured.
            FileNotFoundError: If the file does not exist.
        """
        if self._storage_path is None:
            raise RuntimeError(
                "No storage_path configured. Provide a Path when creating ShadowRecorder."
            )

        loaded: list[ShadowDecision] = []
        with self._storage_path.open("r", encoding="utf-8") as file_handle:
            for line in file_handle:
                stripped = line.strip()
                if stripped:
                    data = json.loads(stripped)
                    loaded.append(ShadowDecision.model_validate(data))

        return loaded

    def clear_memory(self) -> None:
        """Clear the in-memory record list.

        Does not affect the JSONL file if one is configured.
        """
        self._memory.clear()

    @property
    def count(self) -> int:
        """Number of decisions currently held in memory."""
        return len(self._memory)

    @property
    def storage_path(self) -> Path | None:
        """The JSONL file path, or ``None`` if in-memory only."""
        return self._storage_path

    def _append_to_file(self, decision: ShadowDecision) -> None:
        """Append a single decision as a JSON line to the storage file.

        Args:
            decision: The ``ShadowDecision`` to serialise and append.
        """
        assert self._storage_path is not None
        json_line = decision.model_dump_json()
        with self._storage_path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(json_line + "\n")
