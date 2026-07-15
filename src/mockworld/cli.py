"""The ``mockworld`` CLI (REQ-RT-*).

    mockworld run mock:payments                  # stdio MCP server (default)
    mockworld run mock:payments --transport http --port 8931
    mockworld list                               # installed mocks
    mockworld inspect mock:payments              # tools + faults + state, no run
    mockworld validate <mock-dir>                # lint a mock
    mockworld reset --seed 42 --port 8931        # deterministic reset of a live server
    mockworld demo mock:payments                 # prove determinism in one command
"""

from __future__ import annotations

import json
import sys

import click

from . import __version__
from .engine import Engine
from .loader import list_builtin_mocks, load_mock
from .validate import validate_mock


@click.group(help="mockworld — a synthetic internet for agents.")
@click.version_option(__version__, prog_name="mockworld")
def main() -> None:  # pragma: no cover - entry point
    pass


@main.command("list", help="List installed (built-in) mocks.")
def list_cmd() -> None:
    names = list_builtin_mocks()
    if not names:
        click.echo("no mocks installed")
        return
    for name in names:
        loaded = load_mock(f"mock:{name}")
        d = loaded.definition
        click.echo(f"mock:{name:<10} v{d.version}  [{d.fidelity}]  {len(d.tools)} tools  — {d.description.strip().splitlines()[0]}")


@main.command(help="Print a mock's tools, faults, and state shape without running it.")
@click.argument("source")
def inspect(source: str) -> None:
    loaded = load_mock(source)
    d = loaded.definition
    click.echo(f"{click.style(d.name, bold=True)} v{d.version}  [fidelity: {d.fidelity}]")
    click.echo(d.description.strip() + "\n")
    click.echo(click.style("state:", bold=True))
    for name, coll in d.state.items():
        click.echo(f"  {name} (key={coll.key}): {', '.join(coll.fields)}")
    click.echo("\n" + click.style("tools:", bold=True))
    for t in d.tools:
        params = ", ".join(f"{n}:{s.type}{'*' if s.required else ''}" for n, s in t.params.items())
        click.echo(f"  {click.style(t.name, fg='cyan')}({params})")
        if t.faults:
            faults = ", ".join(f.error or f.type for f in t.faults)
            click.echo(f"      faults: {faults}")
    click.echo("\n" + click.style("fault profiles:", bold=True) + " " + ", ".join(d.fault_profiles))


@main.command(help="Lint a mock (schema, handlers, entropy smells, descriptions).")
@click.argument("source")
def validate(source: str) -> None:
    findings = validate_mock(source)
    errors = [f for f in findings if f.level == "error"]
    for f in findings:
        color = "red" if f.level == "error" else "yellow"
        click.echo(f"  {click.style(f.level.upper(), fg=color)}  {f.message}")
    if not findings:
        click.echo(click.style("✓ clean", fg="green"))
    if errors:
        sys.exit(1)


@main.command(help="Run a mock as an MCP server.")
@click.argument("source")
@click.option("--transport", type=click.Choice(["stdio", "http"]), default="stdio")
@click.option("--host", default="127.0.0.1")
@click.option("--port", type=int, default=8931)
@click.option("--seed", type=int, default=0, help="Deterministic initial state.")
@click.option("--faults", default="realistic", help="Fault profile: none | realistic | hostile | <name>.")
@click.option("--store", type=click.Choice(["memory", "sqlite"]), default="memory")
@click.option("--record-trace", type=click.Path(), default=None, help="Write an NDJSON trace to this file.")
def run(source, transport, host, port, seed, faults, store, record_trace) -> None:
    trace_sink = open(record_trace, "w") if record_trace else None
    engine = Engine.from_source(
        source, seed=seed, faults=faults, store=store, run_id=f"cli-{seed}", trace_sink=trace_sink
    )
    from .server import MockServer

    server = MockServer(engine)
    d = engine.definition
    if transport == "stdio":
        import anyio

        # stderr, so stdout stays a clean MCP stream.
        click.echo(f"mockworld {d.name} v{d.version} — stdio — seed {seed} — faults '{faults}'", err=True)
        anyio.run(server.run_stdio)
    else:
        click.echo(f"mockworld {d.name} v{d.version} — http://{host}:{port}/mcp — seed {seed} — faults '{faults}'")
        click.echo(f"  control plane: http://{host}:{port}/control/*")
        server.run_http(host=host, port=port)


@main.command(help="Reset a running HTTP mock's state deterministically to a seed.")
@click.option("--seed", type=int, required=True)
@click.option("--host", default="127.0.0.1")
@click.option("--port", type=int, default=8931)
def reset(seed, host, port) -> None:
    import httpx

    url = f"http://{host}:{port}/control/reset"
    resp = httpx.post(url, json={"seed": seed}, timeout=5)
    click.echo(resp.json())


@main.command(help="Prove determinism: run a scripted scenario twice, show identical results.")
@click.argument("source", default="mock:payments")
@click.option("--seed", type=int, default=42)
def demo(source, seed) -> None:
    import hashlib

    def transcript() -> list:
        e = Engine.from_source(source, seed=seed, faults="realistic")
        cust = e.call("create_customer", {"name": "Ada", "balance": 100000}).data \
            if e.definition.tool("create_customer") else None
        out = []
        tool = e.definition.tools[0]
        for i in range(10):
            args = _demo_args(e, tool, cust, i)
            r = e.call(tool.name, args)
            out.append([r.success, (r.data or {}).get("id") if r.success else r.err.code])
        return out

    t1, t2 = transcript(), transcript()
    h1 = hashlib.sha256(json.dumps(t1).encode()).hexdigest()[:16]
    h2 = hashlib.sha256(json.dumps(t2).encode()).hexdigest()[:16]
    click.echo(f"run 1 digest: {h1}")
    click.echo(f"run 2 digest: {h2}")
    click.echo(click.style(f"identical: {h1 == h2}", fg="green" if h1 == h2 else "red", bold=True))


def _demo_args(engine, tool, cust, i):
    if tool.name == "create_charge" and cust:
        return {"customer_id": cust["id"], "amount": 1000 + i}
    # generic best-effort for other mocks
    args = {}
    for name, spec in tool.params.items():
        if spec.required:
            args[name] = f"demo-{i}" if spec.type == "str" else (i + 1)
    return args


if __name__ == "__main__":  # pragma: no cover
    main()
