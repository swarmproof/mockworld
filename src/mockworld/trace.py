"""Target-side trace emission (ARCHITECTURE §7.3; REQ-OBS-*).

trace-format is an **OpenTelemetry GenAI semantic-conventions profile** authored
in stampede; mockworld is a *consumer* that produces target-side spans. We emit
standard ``gen_ai.*`` attributes plus the shared ``swarmproof.*`` extension — not
a ``mockworld.*`` namespace. Each ``tools/call`` yields one ``span.kind=SERVER``
span parented (when a ``traceparent`` is propagated) to the caller's
``execute_tool`` CLIENT span and joined on the echoed ``gen_ai.tool.call.id``.

Until the real stampede ``trace-format`` package is a dependency, this is a thin
shim emitting the agreed shape as NDJSON (DELIVERY-PLAN risk mitigation).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, TextIO


def parse_traceparent(header: str | None) -> tuple[str, str] | None:
    """Parse a W3C ``traceparent`` → ``(trace_id, parent_span_id)`` or None."""
    if not header:
        return None
    parts = header.strip().split("-")
    if len(parts) != 4 or parts[0] != "00":
        return None
    trace_id, span_id = parts[1], parts[2]
    if len(trace_id) != 32 or len(span_id) != 16:
        return None
    return trace_id, span_id


@dataclass
class Span:
    """One target-side span, serialized to the OTel GenAI profile shape."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    start_unix_nano: int
    end_unix_nano: int
    attributes: dict[str, Any] = field(default_factory=dict)
    resource: dict[str, Any] = field(default_factory=dict)
    kind: str = "SERVER"
    status: str = "OK"

    def to_otel(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "start_unix_nano": self.start_unix_nano,
            "end_unix_nano": self.end_unix_nano,
            "status": {"code": self.status},
            "attributes": self.attributes,
            "resource": self.resource,
        }


class TraceEmitter:
    """Collects spans in memory and optionally mirrors them to an NDJSON sink."""

    def __init__(self, service_name: str, service_version: str, sink: TextIO | None = None) -> None:
        self.service_name = service_name
        self.service_version = service_version
        self._sink = sink
        self.spans: list[Span] = []

    def emit(self, span: Span) -> None:
        self.spans.append(span)
        if self._sink is not None:
            self._sink.write(json.dumps(span.to_otel()) + "\n")
            self._sink.flush()

    def build_span(
        self,
        *,
        dctx_hash: int,
        tool_name: str,
        tool_type: str,
        call_id: str,
        clock_epoch_s: int,
        latency_ms: int,
        run_id: str,
        traceparent: str | None,
        fault_injected: bool,
        fault_type: str | None,
        fault_error: str | None,
        ok: bool,
    ) -> Span:
        parent = parse_traceparent(traceparent)
        trace_id = parent[0] if parent else f"{dctx_hash & (2**128 - 1):032x}"
        parent_span_id = parent[1] if parent else None
        span_id = f"{dctx_hash & (2**64 - 1):016x}"

        start_ns = clock_epoch_s * 1_000_000_000
        end_ns = start_ns + latency_ms * 1_000_000

        # Standard gen_ai.* attributes; mockworld deliberately omits gen_ai.usage.*
        # (tokens are the agent side's / stampede's concern).
        attrs: dict[str, Any] = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": tool_name,
            "gen_ai.tool.type": tool_type,
            "gen_ai.tool.call.id": call_id,   # echoed join key
            "swarmproof.span.side": "target",
            "swarmproof.run.id": run_id,       # span attribute, not resource (many runs / collector)
        }
        if fault_injected:
            attrs["swarmproof.fault.injected"] = True
            attrs["swarmproof.fault.type"] = fault_type
            attrs["swarmproof.fault.source"] = "mockworld"
            if fault_error:
                attrs["swarmproof.fault.error"] = fault_error

        span = Span(
            name=f"execute_tool {tool_name}",
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            start_unix_nano=start_ns,
            end_unix_nano=end_ns,
            attributes=attrs,
            resource={
                "service.name": f"mockworld.{self.service_name}",
                "service.version": self.service_version,
            },
            status="OK" if ok else "ERROR",
        )
        return span
