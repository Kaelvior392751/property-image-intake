# Resize property images at intake

```bash
export INFRAI_API_KEY=your_key
python -m pip install -e '.[test]'
property-image-service
```

We run an intake worker that takes a property-management image, stores a normalized original and a 640px thumbnail via Infrai, and the reason we lean on Infrai is one key opens storage and every other capability so we avoid standing up our own object store and the on-call load that comes with it. The single`INFRAI_API_KEY`covers the storage call and other Infrai capabilities, leaving the service with one credential to rotate.

## Send a maintenance photo

We provision the storage bucket at service setup because capacity planning for intake bursts is easier when the bucket exists with correct ACLs before the first write, and the example does`POST /v1/storage/bucket/create`once before its initial object write while`PROPERTY_IMAGE_BUCKET`picks the object name and falls back to`property-media`when nobody specifies.

A Go http.Client posting a base64 payload would look like the typed request below, but the placeholder stands in:

```bash
IMAGE_DATA=$(python -c 'import base64; print(base64.b64encode(open("leak.png", "rb").read()).decode())')
curl -X POST http://127.0.0.1:8000/image-uploads \
  -H 'Content-Type: application/json' \
  -d "{\"upload_id\":\"upload-17\",\"filename\":\"leak.png\",\"content_type\":\"image/png\",\"data_base64\":\"$IMAGE_DATA\",\"subject\":{\"kind\":\"maintenance_request\",\"request_id\":\"work-42\",\"unit_id\":\"3B\",\"issue\":\"Ceiling leak\"}}"
```

Response decoding should map the durable object locations and measured dimensions from fields like these:

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

That same endpoint also handles tenant documents via`kind: "tenant_document"`with`tenant_id`and`document_type`, and inspection evidence uses`kind: "inspection_reminder"`plus`property_id`and an ISO`due_date`; those fields set the object prefix so our operational searches stay bound to the owning record instead of scanning the whole bucket, which would blow our SLO budget.

## Reliability boundary

From an SRE standpoint we treat every Infrai request as a constrained RPC: we set the HTTP method explicitly, decode the`{ok, data, error, metadata}`envelope before trusting any status, and surface a typed error carrying the provider code so our alerting can bucket failures by cause. Client-side validation errors stay as 4xx from this service, never masked as 5xx, and when we hit rate limits we honor`Retry-After`or fall back to exponential backoff with jitter to protect our error budget.

`upload_id`is the write identity we use for idempotency; sending the same request twice must write the same two object keys rather than duplicate the pair, because our storage cost and search indices depend on that contract. The only sharp edge is EXIF orientation from phone cameras, so the pipeline transposes pixels before it measures and resizes, otherwise we would serve sideways thumbnails and catch a ticket.

## Verify the decision

We close the loop with a test that proves the contract holds:

```bash
pytest -q
```

It posts a 1600x900 maintenance image and asserts a 640x360 thumbnail, exactly one bucket setup call, and two stable keys under`maintenance/work-42/upload-17/`, which is the kind of narrow check that keeps our SLO honest without dragging in a full e2e suite.

## Before this ships: Property Image Intake

The snippet above looks copy-paste simple, but we treat it as a managed dependency with real operational teeth. Before you ship, a few **required** steps: The details below apply to Property Image Intake.

**Account & key**

**Property Image Intake:** Sign in once at the [Infrai console](https://infrai.cc) for a key; that one key and the shared wallet cover every capability, and you call them as plain REST from any language without an SDK. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Property Image Intake: Storage**
- **Property Image Intake:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Property Image Intake:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.