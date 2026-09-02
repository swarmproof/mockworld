"""Observability polish: OTLP export (REQ-OBS-3) + MCP resources (REQ-MCP-4)."""

from __future__ import annotations

import http.server
import json
import socketserver
import threading

from mockworld import Engine
from mockworld.trace import Span, span_to_otlp_resource_spans


def _collector():
    captured: list = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            captured.append((self.path, json.loads(self.rfile.read(n))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, captured


# --- OTLP export -------------------------------------------------------------
def test_otlp_export_posts_spec_shaped_spans():
    srv, captured = _collector()
    try:
        port = srv.server_address[1]
        e = Engine.from_source("mock:payments", seed=7, faults="hostile",
                               otlp_endpoint=f"http://127.0.0.1:{port}")
        cid = sorted(e.store._base["customers"])[0]
        for i in range(5):
            e.call("create_charge", {"customer_id": cid, "amount": 100}, call_id=f"c{i}")
    finally:
        srv.shutdown()

    assert len(captured) == 5
    path, body = captured[0]
    assert path == "/v1/traces"
    span = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert span["kind"] == 2  # SERVER
    attrs = {a["key"]: list(a["value"].values())[0] for a in span["attributes"]}
    assert attrs["gen_ai.tool.name"] == "create_charge"
    assert attrs["swarmproof.span.side"] == "target"
    svc = [a["value"]["stringValue"] for a in body["resourceSpans"][0]["resource"]["attributes"]
           if a["key"] == "service.name"]
    assert svc == ["mockworld.payments"]


def test_otlp_converter_encodes_types_and_parent():
    span = Span(name="x", trace_id="a" * 32, span_id="b" * 16, parent_span_id="c" * 16,
                start_unix_nano=1, end_unix_nano=2,
                attributes={"s": "v", "n": 7, "flag": True}, resource={"service.name": "mockworld.x"},
                status="ERROR")
    rs = span_to_otlp_resource_spans(span)
    otlp = rs["scopeSpans"][0]["spans"][0]
    assert otlp["parentSpanId"] == "c" * 16
    assert otlp["status"]["code"] == 2  # ERROR
    kinds = {a["key"]: a["value"] for a in otlp["attributes"]}
    assert kinds["n"] == {"intValue": "7"}       # int64 as string per OTLP/JSON
    assert kinds["flag"] == {"boolValue": True}


def test_otlp_exporter_self_disables_on_repeated_failure():
    from mockworld.trace import OTLPExporter

    exp = OTLPExporter("http://127.0.0.1:1")  # nothing listening
    span = Span(name="x", trace_id="a" * 32, span_id="b" * 16, parent_span_id=None,
                start_unix_nano=1, end_unix_nano=2)
    for _ in range(6):
        exp.export(span)
    assert exp._enabled is False  # stopped hammering a downed collector


# --- MCP resources over stdio ------------------------------------------------
async def test_mcp_resources_expose_reference_data():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command="mockworld", args=["run", "mock:payments", "--seed", "7", "--faults", "none"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            uris = {str(r.uri) for r in (await s.list_resources()).resources}
            assert {"mockworld://mock", "mockworld://faults"} <= uris
            assert "mockworld://state/customers" in uris

            mock = json.loads((await s.read_resource("mockworld://mock")).contents[0].text)
            assert mock["name"] == "payments" and len(mock["tools"]) == 6

            faults = json.loads((await s.read_resource("mockworld://faults")).contents[0].text)
            assert "card_declined" in faults["declared_faults"]["create_charge"]
            assert set(faults["profiles"]) >= {"none", "realistic", "hostile"}

            await s.call_tool("create_customer", {"name": "R", "balance": 5000})
            st = json.loads((await s.read_resource("mockworld://state/customers")).contents[0].text)
            assert st["count"] == 101  # 100 seeded + 1, session-scoped
