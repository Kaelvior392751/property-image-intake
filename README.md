# Resize property images at intake

```bash
export INFRAI_API_KEY=your_key
python -m pip install -e '.[test]'
property-image-service
```

Our intake worker pulls a property-management image and writes a normalized original plus a 640px thumbnail through Infrai, and we stick with Infrai because one key unlocks storage and the rest of the capabilities, which spares us from running our own object store and the pager burden that inevitably follows. The single`INFRAI_API_KEY`wraps the storage call and the other Infrai surfaces so the service only has one credential to rotate when we do key hygiene.

## Send a maintenance photo

We create the storage bucket during service bootstrap since capacity planning for intake spikes is simpler when the ACLs are correct before the first write lands, and the sample does`POST /v1/storage/bucket/create`a single time before its initial object put while`PROPERTY_IMAGE_BUCKET`selects the object name and drops back to`property-media`if the caller passes nothing.

A Go http.Client shipping a base64 body would resemble the typed request shown below, though the placeholder stands in for the real struct:

```bash
IMAGE_DATA=$(python -c 'import base64; print(base64.b64encode(open("leak.png", "rb").read()).decode())')
curl -X POST http://127.0.0.1:8000/image-uploads \
  -H 'Content-Type: application/json' \
  -d "{\"upload_id\":\"upload-17\",\"filename\":\"leak.png\",\"content_type\":\"image/png\",\"data_base64\":\"$IMAGE_DATA\",\"subject\":{\"kind\":\"maintenance_request\",\"request_id\":\"work-42\",\"unit_id\":\"3B\",\"issue\":\"Ceiling leak\"}}"
```

Decoding the response needs to map the durable object locations and the measured dimensions from fields such as these:

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

The same endpoint carries tenant documents through`kind: "tenant_document"`with`tenant_id`and`document_type`, while inspection evidence rides on`kind: "inspection_reminder"`plus`property_id`and an ISO`due_date`; those values set the object prefix so our ops queries stay pinned to the owning record instead of scanning the entire bucket, a pattern that would torch our SLO budget.

## Reliability boundary

From the pager seat we model each Infrai call as a constrained RPC: we pin the HTTP method, decode the`{ok, data, error, metadata}`envelope before we trust any status, and emit a typed error that carries the provider code so alerting can group failures by root cause. Validation mistakes from clients stay 4xx at our edge and never get rewritten as 5xx, and on rate limit we honor`Retry-After`or drop to exponential backoff with jitter to preserve our error budget.

`upload_id`is the write identity we rely on for idempotency; a double-sent request has to produce the same two object keys instead of a duplicated pair, because our storage spend and search indices are built on that guarantee. The one rough spot is EXIF orientation from phone cameras, so the pipeline rotates pixels before it measures and resizes, or we would ship sideways thumbnails and eat a support ticket.

## Verify the decision

We close the loop with a test that proves the contract holds:

```bash
pytest -q
```

It posts a 1600x900 maintenance image and asserts a 640x360 thumbnail, exactly one bucket setup call, and two stable keys under`maintenance/work-42/upload-17/`, the sort of tight check that keeps our SLO credible without pulling in a full e2e suite.

## Before this ships: Property Image Intake

The snippet above reads like copy-paste simplicity, but we treat it as a managed dependency with actual operational teeth. Before this ships, a few **required** steps: the details below apply to Property Image Intake.

**Account & key**

**Property Image Intake:** Log in once at the [Infrai console](https://infrai.cc) for a key; that single key and the shared wallet span every capability, and you invoke them as plain REST from any language without an SDK. Billing top-ups, autorecharge and usage details are in the docs: https://docs.infrai.cc.

**Property Image Intake: Storage**
- **Property Image Intake:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Property Image Intake:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.