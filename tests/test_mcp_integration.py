"""Integration + observability gates (TEST-PLAN §6: INT-1, INT-4, INT-5, INT-5b)."""

from __future__ import annotations

import json

from mockworld import Engine
from mockworld.control import MockworldTarget


# --- INT-1: MCP initialize + tools/list + tools/call over stdio --------------
async def test_int1_stdio_roundtrip():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command="mockworld", args=["run", "mock:payments", "--seed", "7", "--faults", "none"]
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {"create_charge", "refund_charge", "get_customer"} <= {t.name for t in tools.tools}
            # every tool advertises a non-empty description (REQ-MCP-1)
            assert all(t.description for t in tools.tools)

            cust = (await session.call_tool("create_customer", {"name": "Wire", "balance": 5000})).structuredContent
            charge = await session.call_tool("create_charge", {"customer_id": cust["id"], "amount": 2000})
            assert charge.isError is False
            assert charge.structuredContent["status"] == "succeeded"

            bad = await session.call_tool("refund_charge", {"charge_id": charge.structuredContent["id"], "amount": 999999})
            assert bad.isError is True
            assert json.loads(bad.content[0].text)["error"]["code"] == "refund_exceeds_charge"


# --- INT-4: target-side span shape (OTel GenAI profile) ----------------------
def test_int4_span_shape():
    e = Engine.from_source("mock:payments", seed=7, faults="hostile")
    cid = sorted(e.store._base["customers"])[0]
    for _ in range(30):
        e.call("create_charge", {"customer_id": cid, "amount": 100})

    span = e.tracer.spans[0]
    a = span.attributes
    assert span.kind == "SERVER"
    assert a["gen_ai.operation.name"] == "execute_tool"
    assert a["gen_ai.tool.name"] == "create_charge"
    assert "gen_ai.tool.call.id" in a
    assert a["swarmproof.span.side"] == "target"
    assert span.resource["service.name"] == "mockworld.payments"
    assert not any(k.startswith("gen_ai.usage") for k in a)  # tokens are the agent side's concern

    faulted = [s for s in e.tracer.spans if s.attributes.get("swarmproof.fault.injected")]
    assert faulted, "expected some faults under hostile"
    assert faulted[0].attributes["swarmproof.fault.source"] == "mockworld"


# --- INT-5: trace nesting via propagated traceparent -------------------------
def test_int5_trace_nesting_from_traceparent():
    e = Engine.from_source("mock:payments", seed=7, faults="none")
    cid = sorted(e.store._base["customers"])[0]
    tp = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    e.call("create_charge", {"customer_id": cid, "amount": 100}, call_id="call-xyz", traceparent=tp)
    span = e.tracer.spans[-1]
    assert span.trace_id == "a" * 32              # shares the caller's trace
    assert span.parent_span_id == "b" * 16        # child of the caller's execute_tool span
    assert span.attributes["gen_ai.tool.call.id"] == "call-xyz"  # echoed join key


# --- INT-5b: stampede Target protocol conformance ----------------------------
async def test_int5b_target_protocol():
    t = MockworldTarget(Engine.from_source("mock:payments", seed=7, faults="none"))
    assert {tool["name"] for tool in await t.discover()} >= {"create_charge"}
    assert t.isolation() == "per_agent"
    assert t.safety_descriptor()["sandboxed"] is True
    assert (await t.health())["status"] == "ok"

    # reset(seed) is a pure function of the seed → identical id across resets
    async def first_id():
        await t.reset(7)
        cust = (await t.invoke({"name": "create_customer", "arguments": {"name": "A", "balance": 1000}})).data
        return cust["id"]
    assert await first_id() == await first_id()
