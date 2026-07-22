"""mockworld — a synthetic internet for agents.

Deterministic, LLM-free fake services exposed as MCP servers. This package's
public surface is the mock-authoring ABI (``Result``, ``HandlerCtx``) plus the
:class:`~mockworld.engine.Engine` that runs a mock.
"""

from __future__ import annotations

from .engine import Engine
from .errors import MockError, Result, build_error, register_error
from .handler_ctx import HandlerCtx
from .loader import (
    LoadedMock,
    SeedCtx,
    list_builtin_mocks,
    list_installed_mocks,
    load_mock,
)

__version__ = "0.1.0"

__all__ = [
    "Engine",
    "Result",
    "MockError",
    "HandlerCtx",
    "SeedCtx",
    "LoadedMock",
    "load_mock",
    "list_builtin_mocks",
    "list_installed_mocks",
    "build_error",
    "register_error",
    "__version__",
]
