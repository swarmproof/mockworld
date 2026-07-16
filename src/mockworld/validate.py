"""``mockworld validate`` — the mock linter (REQ-DEF-6; ADR-4 enforcement).

Determinism is a hard contract, so the most important check is the *entropy
smell*: a handler that reads the wall clock or calls ``random``/``uuid`` directly
has escaped the seeded ``ctx`` and will break byte-identical replay. This linter
is a merge gate (G-LINT) run over every built-in mock.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .loader import load_mock, resolve_source
from .schema import MockDef

# Banned ambient-entropy patterns in handler/seed source. hashlib is allowed
# (pure); ctx.rng/ctx.clock/ctx.ids are the sanctioned sources.
_ENTROPY_PATTERNS = [
    (re.compile(r"^\s*import\s+(time|random|uuid)\b", re.M), "imports {0} (use ctx.clock/ctx.rng/ctx.ids)"),
    (re.compile(r"^\s*from\s+(time|random|uuid|datetime)\b", re.M), "imports from {0}"),
    (re.compile(r"^\s*import\s+datetime\b", re.M), "imports datetime (use ctx.clock)"),
    (re.compile(r"\bdatetime\.now\b"), "calls datetime.now() (use ctx.now())"),
    (re.compile(r"\btime\.(time|monotonic|sleep)\b"), "calls time.* (nondeterministic)"),
    (re.compile(r"(?<!ctx\.)\brandom\.(random|randint|choice|uniform|shuffle)\b"), "calls random.* directly (use ctx.rng)"),
    (re.compile(r"\buuid\.(uuid1|uuid4)\b"), "calls uuid.* (use ctx.ids.next())"),
]


@dataclass
class Finding:
    level: str  # "error" | "warn"
    message: str


def _scan_entropy(path: Path, findings: list[Finding]) -> None:
    if not path.exists():
        return
    src = path.read_text()
    for pattern, template in _ENTROPY_PATTERNS:
        m = pattern.search(src)
        if m:
            detail = template.format(*m.groups()) if m.groups() else template
            findings.append(Finding("error", f"{path.name}: entropy smell — {detail}"))


def validate_mock(source: str) -> list[Finding]:
    findings: list[Finding] = []
    path = resolve_source(source)

    if not path.is_dir():
        return [Finding("error", f"not a directory: {path}")]
    if not (path / "mock.yaml").exists():
        return [Finding("error", f"missing mock.yaml in {path}")]

    # 1. Schema validity + load.
    try:
        loaded = load_mock(source)
    except Exception as exc:  # pydantic / yaml / import errors
        return [Finding("error", f"failed to load: {type(exc).__name__}: {exc}")]
    definition: MockDef = loaded.definition

    # 2. Python handlers exist with the right signature.
    for tool in definition.tools:
        if not tool.is_crud:
            fn = getattr(loaded.handlers, tool.handler_name or "", None) if loaded.handlers else None
            if fn is None:
                findings.append(Finding("error", f"tool {tool.name!r}: handler {tool.handler_name!r} not found"))
            elif fn.__code__.co_argcount != 2:
                findings.append(Finding("error", f"handler {tool.handler_name!r} must take (ctx, params)"))

    # 3. Entropy smells in handler/seed source.
    _scan_entropy(path / "handlers.py", findings)
    _scan_entropy(path / "seed.py", findings)

    # 4. Description quality (agent legibility, REQ-MCP-1).
    for tool in definition.tools:
        desc = tool.description.strip()
        if len(desc) < 20:
            findings.append(Finding("warn", f"tool {tool.name!r}: description is thin ({len(desc)} chars)"))

    # 5. Fidelity governance.
    if not (path / "fidelity.md").exists():
        findings.append(Finding("warn", "no fidelity.md (document what this mock does/doesn't model)"))

    return findings
