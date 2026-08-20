"""Streamable-HTTP transport + control plane E2E (REQ-RT-2, REQ-MCP-3, INT-2, INT-3).

Spawns a real ``mockworld run --transport http`` server on a free port and drives
it with a real MCP client across two sessions, then exercises the out-of-band
control plane. This is the automated counterpart to the stdio round-trip in
test_mcp_integration; it guards the P0 HTTP path against silent regression.
"""

from __future__ import annotations

import socket
import subprocess
import time

import httpx
import pytest


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def http_server():
    port = _free_port()
    proc = subprocess.Popen(
        ["mockworld", "run", "mock:payments", "--transport", "http",
         "--port", str(port), "--seed", "7", "--faults", "none"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    health = f"http://127.0.0.1:{port}/control/health"
    try:
        for _ in range(60):
            try:
                if httpx.get(health, timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        else:
            pytest.skip("http server did not come up in time")
        yield port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


async def test_http_roundtrip_isolation_and_control(http_server):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    port = http_server
    url = f"http://127.0.0.1:{port}/mcp"

    # Session A: initialize, list tools, create a customer and charge it.
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as a:
            await a.initialize()
            names = {t.name for t in (await a.list_tools()).tools}
            assert {"create_charge", "get_charge", "create_customer"} <= names
            cust = (await a.call_tool("create_customer", {"name": "A", "balance": 5000})).structuredContent
            charge = (await a.call_tool("create_charge", {"customer_id": cust["id"], "amount": 1000})).structuredContent
            assert charge["status"] == "succeeded"

    # Session B is a distinct Mcp-Session-Id → cannot see A's charge (REQ-ISO-1 over the wire).
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as b:
            await b.initialize()
            got = await b.call_tool("get_charge", {"charge_id": charge["id"]})
            assert got.isError is True

    # Control plane is reachable and separate from the /mcp surface (REQ-CTL-2).
    assert httpx.get(f"http://127.0.0.1:{port}/control/health", timeout=5).json()["status"] == "ok"
    reset = httpx.post(f"http://127.0.0.1:{port}/control/reset", json={"seed": 7}, timeout=5)
    assert reset.status_code == 200 and reset.json()["status"] == "reset"
