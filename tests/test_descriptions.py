"""Ambiguous-description variants (REQ-MCP-6) + the misuse A/B they enable."""

from __future__ import annotations

import json

from mockworld import Engine
from mockworld.swarm import run_swarm


def test_effective_description_honors_mode():
    clear = Engine.from_source("mock:crm", seed=1, descriptions="clear")
    ambig = Engine.from_source("mock:crm", seed=1, descriptions="ambiguous")
    delete = clear.definition.tool("delete_record")
    assert "PERMANENTLY" in clear.effective_description(delete)
    assert ambig.effective_description(delete) == "Remove a record from the list."


def test_ambiguous_makes_archive_and_delete_indistinguishable():
    e = Engine.from_source("mock:crm", seed=1, descriptions="ambiguous")
    archive = e.effective_description(e.definition.tool("archive_record"))
    delete = e.effective_description(e.definition.tool("delete_record"))
    assert archive == delete  # an agent literally cannot tell them apart


def test_tool_without_variant_falls_back():
    # payments.create_charge declares no ambiguous variant → same text either way.
    a = Engine.from_source("mock:payments", seed=1, descriptions="ambiguous")
    b = Engine.from_source("mock:payments", seed=1, descriptions="clear")
    t = a.definition.tool("create_charge")
    assert a.effective_description(t) == b.effective_description(t)


def test_misuse_rate_rises_under_ambiguous_descriptions():
    def rate(mode: str) -> float:
        e = Engine.from_source("mock:crm", seed=42, faults="none", descriptions=mode)
        return run_swarm(e, agents=200, goal="hide", seed=42).misuse["delete_rate"]

    clear, ambiguous = rate("clear"), rate("ambiguous")
    assert ambiguous > clear                 # vague descriptions → more destroyed data
    assert rate("ambiguous") == ambiguous    # deterministic / reproducible


async def test_mcp_serves_ambiguous_descriptions_over_the_wire():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command="mockworld", args=["run", "mock:crm", "--seed", "1", "--descriptions", "ambiguous"]
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            tools = {t.name: t.description for t in (await s.list_tools()).tools}
            assert tools["delete_record"] == "Remove a record from the list."
            assert tools["archive_record"] == tools["delete_record"]
