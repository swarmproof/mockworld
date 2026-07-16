"""files handlers — the stateful invariants a fake S3 must enforce.

  * read-after-write consistency: immediately after put_object, get_object and
    list_objects reflect the write (ties to the E2E-6 scenario).
  * versioning: the first write of a key is version 1; overwriting an existing
    key increments `version` and mints a new `etag`.

All entropy comes from `ctx` (clock/ids/rng). ``hashlib`` is a pure function of
its input (no wall clock / no unseeded randomness), so etags stay byte-identical
under a fixed seed. Importing time/random/uuid here would break determinism.
"""

from __future__ import annotations

import hashlib

from mockworld import Result


def _etag(key: str, version: int) -> str:
    """A deterministic, S3-shaped hex etag derived from key + version.

    Pure function of its inputs: same (key, version) always hashes to the same
    etag, and a version bump on overwrite changes it.
    """
    return hashlib.md5(f"{key}:{version}".encode()).hexdigest()  # noqa: S324 - non-crypto id


def put_object(ctx, params) -> Result:
    key = params["key"]
    prior = ctx.state.objects.get(key)
    version = prior["version"] + 1 if prior is not None else 1  # first write is v1

    obj = {
        "key": key,
        "bucket": params.get("bucket", "default"),
        "size": params.get("size", 0),
        "content_type": params.get("content_type", "application/octet-stream"),
        "version": version,
        "etag": _etag(key, version),
        # A create keeps its original timestamp; an overwrite records the new one.
        "created": prior["created"] if prior is not None else ctx.now(),
    }
    ctx.state.objects.put(key, obj)
    return Result.ok(obj)


def get_object(ctx, params) -> Result:
    obj = ctx.state.objects.get(params["key"])
    if obj is None:
        return Result.error("no_such_key", f"No such key: {params['key']}")
    return Result.ok(obj)


def list_objects(ctx, params) -> Result:
    prefix = params.get("prefix")
    bucket = params.get("bucket")

    objs = ctx.state.objects.all()  # already key-sorted (stable order)
    if prefix:
        objs = [o for o in objs if o["key"].startswith(prefix)]
    if bucket:
        objs = [o for o in objs if o.get("bucket") == bucket]

    return Result.ok({"data": objs, "count": len(objs)})


def delete_object(ctx, params) -> Result:
    key = params["key"]
    if not ctx.state.objects.exists(key):
        return Result.error("no_such_key", f"No such key: {key}")
    ctx.state.objects.delete(key)
    return Result.ok({"key": key, "deleted": True})
