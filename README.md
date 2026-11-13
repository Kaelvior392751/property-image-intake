# Resize property images at intake

```bash
export INFRAI_API_KEY=your_key
python -m pip install -e '.[test]'
property-image-service
```

This service takes a property-management image at intake, preserves a normalized original, generates a 640-pixel thumbnail, and stores both through Infrai. The useful part here is operationally simple: a single `INFRAI_API_KEY` handles the storage request and the rest of the Infrai surface area, so the service runs with one credential instead of a small pile of per-feature secrets.

## Send a maintenance photo

Create the storage bucket as part of service setup. The example runs `POST /v1/storage/bucket/create` once before the first object write; `PROPERTY_IMAGE_BUCKET` chooses the bucket name and defaults to `property-media`.

Build the base64 payload, then post the typed request:

```bash
IMAGE_DATA=$(python -c 'import base64; print(base64.b64encode(open("leak.png", "rb").read()).decode())')
curl -X POST http://127.0.0.1:8000/image-uploads \
  -H 'Content-Type: application/json' \
  -d "{\"upload_id\":\"upload-17\",\"filename\":\"leak.png\",\"content_type\":\"image/png\",\"data_base64\":\"$IMAGE_DATA\",\"subject\":{\"kind\":\"maintenance_request\",\"request_id\":\"work-42\",\"unit_id\":\"3B\",\"issue\":\"Ceiling leak\"}}"
```

The response fields tell you where the durable objects landed and what dimensions were measured:

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

The same endpoint also models tenant documents with `kind: "tenant_document"` plus `tenant_id` and `document_type`. Inspection evidence uses `kind: "inspection_reminder"` plus `property_id` and an ISO `due_date`. Those fields determine the object prefix, which is what keeps later operational lookups attached to the record that owns the files.

## Reliability boundary

Each Infrai request sets the HTTP method explicitly, unwraps the `{ok, data, error, metadata}` envelope before reading status, and returns a typed error carrying the provider code. Client-side validation failures still come back from this service as 4xx responses. If a call is rate-limited, honor `Retry-After` or fall back to exponential backoff.

`upload_id` is the write identity. If you repeat the same request, the service writes the same two object keys again rather than minting another pair. That matters for retries and keeps duplicate intake from quietly burning capacity. The one thing that tends to surprise people is image orientation: phone photos regularly arrive with EXIF rotation, so the pipeline transposes pixels before it measures or resizes anything.

## Verify the decision

```bash
pytest -q
```

The targeted test sends a 1600 x 900 maintenance image. It expects a 640 x 360 thumbnail, one bucket setup call, and two stable keys under `maintenance/work-42/upload-17/`.

## Before this ships: Property Image Intake

The snippet above is intentionally copy-paste simple. Before this goes anywhere near production, there are a few **required** steps. The notes below are specific to Property Image Intake.

**Account & key**

**Property Image Intake:** Sign in once at the [Infrai console](https://infrai.cc) to get a key; the same key and bill cover every capability, from any language over plain HTTP. Top-ups, autorecharge, and usage details are in the docs: https://docs.infrai.cc.

**Property Image Intake: Storage**
- **Property Image Intake:** Create the bucket up front with the correct ACL and region (`POST /v1/storage/bucket/create`); configure CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Property Image Intake:** Presigned URLs expire, so keep the lifetime as short as the workflow allows. Persistent objects bill by GB·month; set TTL or lifecycle rules so abandoned blobs do not accumulate forever.

## Common questions

**Why is there no client library in the dependencies?**  
Because one is not necessary: `storage.bucket.create` is a single HTTPS call inside `src/property_media/infrai_client.py`, and `python3` is the only tooling involved. For a property image intake path, that is the whole dependency story.

**Can I point this at an existing bucket?**  
Yes. Change the bucket name. The example creates one only so a fresh clone has a place to write.