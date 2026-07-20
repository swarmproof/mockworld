"""Record-mode: scaffold a mock from an OpenAPI spec (ROADMAP v0.2; REQ-REC-*).

OpenAPI describes *shapes*, not stateful *semantics*, so this produces a runnable
scaffold — declarative CRUD wherever a standard REST pattern is recognized, a
marked Python handler stub everywhere else — that the author then fills in with
the interesting invariants (ARCHITECTURE §9). Synthetic seed data only; example
values that look like secrets/PII are never copied (REQ-REC-2).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml

_JSON_TO_PARAM = {
    "string": "str", "integer": "int", "number": "float",
    "boolean": "bool", "array": "list", "object": "dict",
}
_SECRET_HINT = re.compile(r"(password|secret|token|api[_-]?key|authorization|credential)", re.I)


def _snake(s: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s)
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
    return re.sub(r"_+", "_", s).strip("_").lower()


def _resource_of(path: str) -> str | None:
    """First non-parameter path segment → collection name (``/v1/customers/{id}`` → customers)."""
    for seg in path.strip("/").split("/"):
        if seg and not seg.startswith("{") and seg not in ("v1", "v2", "api"):
            return _snake(seg)
    return None


def _crud_op(method: str, path: str) -> str | None:
    """Map only *simple* REST shapes to CRUD; sub-resource actions get a stub."""
    segs = [s for s in path.strip("/").split("/") if s not in ("v1", "v2", "api")]
    method = method.lower()
    # /collection
    if len(segs) == 1 and not segs[0].startswith("{"):
        return {"get": "list", "post": "create"}.get(method)
    # /collection/{id}
    if len(segs) == 2 and not segs[0].startswith("{") and segs[1].startswith("{"):
        return {"get": "read", "put": "update", "patch": "update", "delete": "delete"}.get(method)
    return None  # e.g. /pets/{id}/adopt → custom action → python handler stub


def _collect_params(operation: dict, spec: dict) -> dict[str, dict]:
    params: dict[str, dict] = {}
    for p in operation.get("parameters", []):
        p = _deref(p, spec)
        name = p.get("name")
        if not name or _SECRET_HINT.search(name):
            continue
        schema = p.get("schema", {})
        params[_snake(name)] = {
            "type": _JSON_TO_PARAM.get(schema.get("type", "string"), "str"),
            "required": bool(p.get("required", p.get("in") == "path")),
        }
    body = operation.get("requestBody")
    if body:
        schema = _request_schema(body, spec)
        for pname, pschema in (schema.get("properties") or {}).items():
            if _SECRET_HINT.search(pname):
                continue
            required = pname in (schema.get("required") or [])
            params[_snake(pname)] = {
                "type": _JSON_TO_PARAM.get(pschema.get("type", "string"), "str"),
                "required": required,
            }
    return params


def _deref(obj: dict, spec: dict) -> dict:
    ref = obj.get("$ref")
    if not ref or not ref.startswith("#/"):
        return obj
    node: Any = spec
    for part in ref[2:].split("/"):
        node = node.get(part, {})
    return node


def _request_schema(body: dict, spec: dict) -> dict:
    body = _deref(body, spec)
    content = body.get("content", {})
    media = content.get("application/json") or next(iter(content.values()), {})
    return _deref(media.get("schema", {}), spec)


def _infer_fields(resource: str, spec: dict) -> dict[str, str]:
    """Find a component schema for the resource and turn its properties into fields."""
    schemas = spec.get("components", {}).get("schemas", {})
    singular = resource[:-1] if resource.endswith("s") else resource
    for cand in (resource, singular, resource.capitalize(), singular.capitalize()):
        schema = schemas.get(cand)
        if schema:
            fields = {}
            for pname, pschema in (schema.get("properties") or {}).items():
                if _SECRET_HINT.search(pname):
                    continue
                fields[_snake(pname)] = _JSON_TO_PARAM.get(pschema.get("type", "string"), "str")
            fields.setdefault("id", "str")
            return fields
    return {"id": "str", "name": "str"}


def from_openapi(spec_path: str, name: str | None = None, out_dir: str | None = None) -> Path:
    with open(spec_path) as f:
        spec = yaml.safe_load(f)

    mock_name = _snake(name or spec.get("info", {}).get("title", "recorded"))
    out = Path(out_dir) if out_dir else Path.cwd() / mock_name
    out.mkdir(parents=True, exist_ok=True)

    tools: list[dict] = []
    handler_stubs: list[str] = []
    collections: dict[str, dict] = {}
    key_field: dict[str, str] = {}

    for path, item in (spec.get("paths") or {}).items():
        resource = _resource_of(path)
        for method, operation in item.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            op_id = operation.get("operationId") or f"{method}_{resource or 'root'}"
            tname = _snake(op_id)
            desc = (operation.get("summary") or operation.get("description")
                    or f"{method.upper()} {path}").strip().split("\n")[0]
            params = _collect_params(operation, spec)
            op = _crud_op(method, path) if resource else None

            tool: dict[str, Any] = {"name": tname, "description": desc, "params": params or {}}
            if op and resource:
                collections.setdefault(resource, {}).update(_infer_fields(resource, spec))
                key_field[resource] = "id"
                tool["behavior"] = f"crud:{op}"
                tool["collection"] = resource
            else:
                tool["behavior"] = f"python:handlers.{tname}"
                handler_stubs.append(tname)
            tools.append(tool)

    _write_scaffold(out, mock_name, spec, tools, collections, key_field, handler_stubs)
    return out


# An id-looking path segment: all digits, a long hex/uuid, or a prefixed id whose
# suffix contains a digit (ord_1, cus_abc9) — but NOT plain nouns like order_items.
_ID_SEGMENT = re.compile(r"^(\d+|[0-9a-fA-F-]{16,}|[A-Za-z]+[_-][0-9A-Za-z]*\d[0-9A-Za-z]*)$")


def _py_type_of(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "str"


def _templatize(path: str) -> str:
    """Collapse concrete id-looking segments so /pets/123 and /pets/456 share a template."""
    return "/".join("{id}" if _ID_SEGMENT.match(seg) else seg for seg in path.split("/"))


def _fields_from_body(body: Any) -> dict[str, str]:
    sample = body
    if isinstance(body, dict):
        for wrapper in ("data", "items", "results"):
            if isinstance(body.get(wrapper), list) and body[wrapper]:
                sample = body[wrapper][0]
                break
    if isinstance(sample, list) and sample:
        sample = sample[0]
    if not isinstance(sample, dict):
        return {}
    return {
        _snake(k): _py_type_of(v)
        for k, v in sample.items()
        if not _SECRET_HINT.search(k)
    }


def _parse_json(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def from_har(har_path: str, name: str | None = None, out_dir: str | None = None) -> Path:
    """Scaffold a mock from a captured HAR (traffic) file (REQ-REC-1, F2).

    Infers tools, collections, and field shapes from *observed* request/response
    pairs. Concrete id path-segments are templatized so repeated calls collapse to
    one tool. Only shapes are learned — no captured values (and no secret/PII-named
    fields) are persisted (REQ-REC-2).
    """
    with open(har_path) as f:
        har = json.load(f)

    mock_name = _snake(name or "recorded")
    out = Path(out_dir) if out_dir else Path.cwd() / mock_name
    out.mkdir(parents=True, exist_ok=True)

    seen: dict[tuple[str, str], dict] = {}  # (method, template) -> best sample
    for entry in har.get("log", {}).get("entries", []):
        req = entry.get("request", {})
        method = (req.get("method") or "GET").lower()
        parsed = urlparse(req.get("url", ""))
        template = _templatize(parsed.path)
        body = _parse_json((entry.get("response") or {}).get("content", {}).get("text"))
        query = {_snake(k): "str" for k in parse_qs(parsed.query) if not _SECRET_HINT.search(k)}
        req_body = _parse_json((req.get("postData") or {}).get("text"))
        body_params = (
            {_snake(k): _py_type_of(v) for k, v in req_body.items() if not _SECRET_HINT.search(k)}
            if isinstance(req_body, dict) else {}
        )
        key = (method, template)
        if key not in seen or (body is not None and seen[key].get("body") is None):
            seen[key] = {"path": parsed.path, "template": template, "body": body,
                         "params": {**query, **body_params}}

    tools: list[dict] = []
    handler_stubs: list[str] = []
    collections: dict[str, dict] = {}
    key_field: dict[str, str] = {}

    for (method, template), info in sorted(seen.items()):
        resource = _resource_of(template)
        op = _crud_op(method, template) if resource else None
        tname = _har_tool_name(method, template, op, resource)
        params = {k: {"type": t, "required": False} for k, t in info["params"].items()}
        if op in ("read", "update", "delete"):
            params.setdefault("id", {"type": "str", "required": True})

        tool: dict[str, Any] = {"name": tname, "description": f"{method.upper()} {template}", "params": params}
        if op and resource:
            fields = _fields_from_body(info["body"]) or {"id": "str"}
            fields.setdefault("id", "str")
            collections.setdefault(resource, {}).update(fields)
            key_field[resource] = "id"
            tool["behavior"] = f"crud:{op}"
            tool["collection"] = resource
        else:
            tool["behavior"] = f"python:handlers.{tname}"
            handler_stubs.append(tname)
        tools.append(tool)

    synthetic_spec = {"info": {"title": mock_name, "description": "Scaffolded from a HAR capture."}}
    _write_scaffold(out, mock_name, synthetic_spec, tools, collections, key_field, handler_stubs)
    return out


def _har_tool_name(method: str, template: str, op: str | None, resource: str | None) -> str:
    singular = (resource[:-1] if resource and resource.endswith("s") else resource) or "root"
    names = {"list": f"list_{resource}", "read": f"get_{singular}", "create": f"create_{singular}",
             "update": f"update_{singular}", "delete": f"delete_{singular}"}
    if op in names:
        return _snake(names[op])
    last = [s for s in template.strip("/").split("/")
            if not s.startswith("{") and s not in ("v1", "v2", "api")]
    return _snake(f"{method}_{'_'.join(last) or 'root'}")


def _write_scaffold(out, mock_name, spec, tools, collections, key_field, handler_stubs) -> None:
    state = {
        coll: {"key": key_field.get(coll, "id"), "fields": fields}
        for coll, fields in collections.items()
    }
    definition = {
        "schema_version": "1",
        "name": mock_name,
        "version": "0.1.0",
        "description": (spec.get("info", {}).get("description")
                        or f"Scaffolded from OpenAPI: {spec.get('info', {}).get('title', mock_name)}."),
        "fidelity": "sketch",
        "state": state,
        "seed": {"generator": "builtin", "volume": {c: 20 for c in collections}},
        "tools": tools,
        "fault_profiles": {"none": {}, "realistic": {"inherit": "tool_defaults"}},
    }
    with open(out / "mock.yaml", "w") as f:
        yaml.safe_dump(definition, f, sort_keys=False, default_flow_style=False)

    if handler_stubs:
        lines = [
            '"""Scaffolded handlers — FILL IN the stateful behavior these tools should model."""',
            "",
            "from mockworld import Result",
            "",
            "",
        ]
        for name in handler_stubs:
            lines += [
                f"def {name}(ctx, params) -> Result:",
                f'    # TODO: implement {name}. Use ctx.state / ctx.ids / ctx.now() — never wall-clock.',
                '    return Result.error("not_implemented", "scaffolded tool — implement me")',
                "",
                "",
            ]
        (out / "handlers.py").write_text("\n".join(lines))

    (out / "fidelity.md").write_text(
        f"# fidelity — mock:{mock_name} (scaffolded)\n\n"
        "**Fidelity level:** `sketch` — generated from an OpenAPI spec by `mockworld record`.\n\n"
        "## Status\n"
        "- CRUD tools that matched standard REST patterns are runnable as-is.\n"
        "- Tools with a `python:handlers.*` stub return `not_implemented` until you write them.\n"
        "- Seed data is synthetic; no real values from the spec were copied. Secret/PII-named "
        "fields were dropped.\n\n"
        "## TODO for the author\n"
        "- Encode stateful invariants (the things agents actually stress).\n"
        "- Declare realistic faults per tool.\n"
        "- Run `mockworld validate` and tighten tool descriptions for agent legibility.\n"
    )
