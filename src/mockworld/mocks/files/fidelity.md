# mock:files — fidelity notes

**Models:** S3-shaped object storage (Amazon S3 / any bucket+key blob store).
**Fidelity:** `partial` — the metadata plane and its invariants are faithful; the
byte plane is not (objects carry no payload, only a declared `size`).

## What is faithful

- **Key-addressed objects.** An object is addressed by a string `key` (the
  collection's primary key). Keys are opaque paths (`report.pdf`,
  `uploads/2023/report.pdf`).
- **Read-after-write consistency.** Immediately after `put_object(key)`,
  `get_object(key)` returns it and `list_objects()` includes it. There is no
  eventual-consistency window (matches modern S3 strong read-after-write).
- **Versioning.** The first write of a key is `version: 1`. Overwriting an
  existing key increments `version` and mints a new `etag`. `etag = md5(key:version)`
  — deterministic and stable under a fixed seed, changing only on overwrite.
- **Stable list order.** `list_objects` returns objects in key-sorted order under
  a `{data, count}` envelope, filtered by `prefix` and/or `bucket`.
- **S3-shaped errors.** A missing key returns `no_such_key` (HTTP 404, body
  `{code: NoSuchKey}`). Denied access returns `access_denied` (HTTP 403, body
  `{code: AccessDenied}`).

## What is NOT modeled (sketch / omitted)

- **No object bytes.** Objects store metadata only (`size`, `content_type`,
  `etag`); there is no upload/download of real content, no range reads, no
  multipart uploads.
- **No bucket lifecycle.** Buckets are a plain string field on the object, not a
  first-class resource — there is no create/delete-bucket, no bucket policies,
  no per-bucket ACLs.
- **No true version history.** `version` is a monotonically increasing counter;
  prior versions are not retained or independently retrievable.
- **etag is not a content hash.** Real S3 etags hash object bytes (and encode
  multipart structure). Here there are no bytes, so the etag hashes `key:version`
  instead — it still satisfies "changes on overwrite" but is not content-derived.
- **No presigned URLs, tags, storage classes, or encryption metadata.**

## Faults

Declared per tool in `mock.yaml`; amplified by the `hostile` profile.

| Fault | Tool(s) | Trigger | Behavior |
|-------|---------|---------|----------|
| `access_denied` | `get_object`, `put_object` | `when` key is under `protected/`, or a low probability roll | Short-circuits with HTTP 403 `{code: AccessDenied}`; no state change |
| `slow_download` | `get_object` | always sampled (latency distribution) | See mapping below |

### `slow_download` maps to a `latency` fault

There is no distinct "slow_download" fault type. It is modeled as a **`latency`**
fault on `get_object` with `distribution: {p50_ms: 50, p99_ms: 3000}`. The engine
samples this distribution deterministically (a per-tool seeded draw), records the
result in `result.meta['latency_ms']`, and — only in real-time demo mode
(`apply_latency=True`) — actually sleeps for that long. Under deterministic tests
the wall clock never advances; the recorded `latency_ms` *is* the observable
"slow download". A large `p99_ms` means occasional multi-second tail fetches that
an agent must tolerate (retry/backoff) without treating them as failures.

### Fault profiles

- `none` — no faults; pure business logic.
- `realistic` — inherits the per-tool defaults above (occasional access denials,
  latency on every get).
- `hostile` — inherits defaults, then elevates `access_denied` to 0.50 on
  `get_object` and 0.40 on `put_object`.
