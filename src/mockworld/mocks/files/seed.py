"""Deterministic base dataset for mock:files (REQ-STATE-2).

Pure function of the seed: same seed -> identical objects, so a fixed key
resolves to the same size/version/etag on every run (the anchor for reproducible
list ordering and read-after-write scenarios).
"""

from __future__ import annotations

import hashlib

_BUCKETS = ["default", "uploads", "backups"]
_EXTENSIONS = [
    ("pdf", "application/pdf"),
    ("txt", "text/plain"),
    ("json", "application/json"),
    ("csv", "text/csv"),
    ("png", "image/png"),
]


def _etag(key: str, version: int) -> str:
    return hashlib.md5(f"{key}:{version}".encode()).hexdigest()  # noqa: S324 - non-crypto id


def generate(ctx, definition) -> dict:
    volume = definition.seed.volume
    objects: dict[str, dict] = {}

    base_ts = 1_700_000_000
    for i in range(volume.get("objects", 0)):
        ext, content_type = ctx.fake.choice(_EXTENSIONS)
        # A folder-ish, unique key: <word>/<word>-<n>.<ext>
        name = f"{ctx.fake.word()}/{ctx.fake.word()}-{i}.{ext}"
        objects[name] = {
            "key": name,
            "bucket": ctx.fake.choice(_BUCKETS),
            "size": ctx.rng.randint(1, 5_000_000),
            "content_type": content_type,
            "version": 1,
            "etag": _etag(name, 1),
            "created": base_ts + i,
        }

    return {"objects": objects}
