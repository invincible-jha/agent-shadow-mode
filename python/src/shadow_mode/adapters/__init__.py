# SPDX-License-Identifier: BSL-1.1
# Copyright (c) 2026 MuVeraAI Corporation

"""Shadow mode adapters — framework-specific side-effect interception."""

from .base import ShadowAdapter
from .crewai import CrewAIAdapter
from .generic import GenericAdapter
from .langchain import LangChainAdapter

__all__ = [
    "ShadowAdapter",
    "GenericAdapter",
    "LangChainAdapter",
    "CrewAIAdapter",
]
