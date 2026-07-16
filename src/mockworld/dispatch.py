"""Behavior dispatch: declarative CRUD, or a Python handler (ARCHITECTURE §4.3).

80% of a mock is CRUD against declared state and needs no code (REQ-DEF-3); the
interesting 20% binds a Python handler via the ABI ``fn(ctx, params) -> Result``
(REQ-DEF-4). This module is where a tool call becomes a state mutation.
"""

from __future__ import annotations

from types import ModuleType
from typing import Any

from .errors import Result
from .handler_ctx import HandlerCtx
from .schema import MockDef, ToolDef


class BehaviorDispatcher:
    def __init__(self, mock: MockDef, handlers: ModuleType | None) -> None:
        self._mock = mock
        self._handlers = handlers

    def dispatch(self, tool: ToolDef, ctx: HandlerCtx, params: dict[str, Any]) -> Result:
        if tool.is_crud:
            return self._crud(tool, ctx, params)
        return self._python(tool, ctx, params)

    # -- python handler ABI ------------------------------------------------------

    def _python(self, tool: ToolDef, ctx: HandlerCtx, params: dict[str, Any]) -> Result:
        fn = getattr(self._handlers, tool.handler_name or "", None)
        if fn is None:
            return Result.error(
                "internal_error",
                f"handler {tool.handler_name!r} not found for tool {tool.name!r}",
            )
        result = fn(ctx, params)
        if not isinstance(result, Result):
            raise TypeError(
                f"handler {tool.handler_name!r} must return a Result, got {type(result).__name__}"
            )
        return result

    # -- declarative CRUD --------------------------------------------------------

    def _crud(self, tool: ToolDef, ctx: HandlerCtx, params: dict[str, Any]) -> Result:
        coll_def = self._mock.state[tool.collection]  # validated to exist at load
        key_field = coll_def.key
        collection = ctx.state.collection(tool.collection)
        op = tool.crud_op

        if op == "create":
            key = params.get(key_field) or ctx.ids.next(tool.collection[:3])
            entity = {key_field: key, **{k: v for k, v in params.items() if k != key_field}}
            collection.put(key, entity)
            return Result.ok(entity)

        if op == "list":
            return Result.ok({"data": collection.all(), "count": collection.count()})

        key = self._lookup_key(tool, params, key_field)
        if op == "read":
            entity = collection.get(key) if key is not None else None
            return Result.ok(entity) if entity else Result.error("not_found", f"No such {tool.collection[:-1]}: {key}")

        if op == "update":
            entity = collection.get(key) if key is not None else None
            if not entity:
                return Result.error("not_found", f"No such {tool.collection[:-1]}: {key}")
            entity.update({k: v for k, v in params.items() if k != key_field})
            collection.put(key, entity)
            return Result.ok(entity)

        if op == "delete":
            existed = collection.delete(key) if key is not None else False
            if not existed:
                return Result.error("not_found", f"No such {tool.collection[:-1]}: {key}")
            return Result.ok({key_field: key, "deleted": True})

        return Result.error("internal_error", f"unhandled crud op {op!r}")

    @staticmethod
    def _lookup_key(tool: ToolDef, params: dict[str, Any], key_field: str) -> Any:
        # Prefer a param named exactly like the collection key; else the first
        # declared param (convention: get_customer(customer_id) → customers.id).
        if key_field in params:
            return params[key_field]
        if tool.params:
            first = next(iter(tool.params))
            return params.get(first)
        return None
