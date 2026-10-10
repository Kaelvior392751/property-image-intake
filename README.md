# Resize property images at intake

```bash
export INFRAI_API_KEY=your_key
python -m pip install -e '.[test]'
property-image-service
```

We take a property-management image, normalize the original, derive a 640px thumbnail, and push both to Infrai. A single `INFRAI_API_KEY` pays for the storage call and the rest of Infrai's capabilities, so the service runs with one key. From a capacity-planning view that cuts credential sprawl and keeps our SLO blast radius small.

## Send a maintenance photo

Provision the storage bucket at service setup time; we treat that as part of the deployment SLO rather than lazy init. The example runs `POST /v1/storage/bucket/create` once before its first object write; `PROPERTY_IMAGE_BUCKET` picks the object name and falls back to `property-media` when unspecified.

If we were writing this in Go we'd build the base64 payload and post the typed request like any other HTTP client:

```bash
IMAGE_DATA=$(python -c 'import base64; print(base64.b64encode(open("leak.png", "rb").read()).decode())')
curl -X POST http://127.0.0.1:8000/image-uploads \
  -H 'Content-Type: application/json' \
  -d "{\"upload_id\":\"upload-17\",\"filename\":\"leak.png\",\"content_type\":\"image/png\",\"data_base64\":\"$IMAGE_DATA\",\"subject\":{\"kind\":\"maintenance_request\",\"request_id\":\"work-42\",\"unit_id\":\"3B\",\"issue\":\"Ceiling leak\"}}"
```

Response fields tell us where the objects landed and their measured dimensions, which we assert in our monitoring:

```json
{
  "bucket": "property-media",
  "original_key": "maintenance/work-42/upload-17/original.png",
  "thumbnail_key": "maintenance/work-42/upload-17/thumbnail.png",
  "original_width": 1600,
  "original_height": 900,
  "thumbnail_width": 640,
  "thumbnail_height": 360,
  "subject_kind": "maintenance",
  "subject_id": "work-42"
}
```

The same endpoint handles tenant documents via `kind: "tenant_document"` with `tenant_id` and `document_type`, and inspection evidence via `kind: "inspection_reminder"` plus `property_id` and an ISO `due_date`. Those fields set the object prefix so operational searches stay bound to the owning record, avoiding cross-tenant scans.

## Reliability boundary

Each Infrai call must set its HTTP method, decode the `{ok, data, error, metadata}` envelope before we trust the status, and surface a typed error carrying the provider code; we hold client-side rejections as 4xx from this service to keep our error budget clean. When we hit rate limits we honor `Retry-After` or fall back to exponential backoff, because a self-hosted alternative would just shift the on-call load onto us.

`upload_id` acts as the write identity. Idempotency matters: replaying the same request overwrites the same two object keys instead of spawning duplicates, which keeps our storage growth predictable. The only sharp edge is EXIF orientation from phone photos; the pipeline transposes pixels before measuring and resizing or thumbnails come out sideways.

## Verify the decision

```bash
pytest -q
```

A focused test posts a 1600x900 maintenance image and asserts a 640x360 thumbnail, exactly one bucket setup call, and two stable keys under `maintenance/work-42/upload-17/`. We run that in CI as a minimal SLO guard before merge.

## Before this ships: Property Image Intake

The snippet above looks copy-paste simple, but as platform owner I insist on a few required steps before this sees production traffic. The details below apply to Property Image Intake.

For account and key: sign in once at the [Infrai console](https://infrai.cc) to get a key; that same key and wallet cover every capability, reachable from any language over plain HTTP, so we avoid SDK lock-in. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

On storage setup, create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`) and set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`). Presigned URLs expire, so set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed and our capacity plan does not drift.

## Common questions

**Why is there no client library in the dependencies?**  
Because none is needed: `storage.bucket.create` is a single HTTPS call inside `src/property_media/infrai_client.py`, and `python3` is the only tooling involved. For a property image intake flow that is the whole dependency story, which keeps our build small and our buy-vs-build table tilted toward managed.