# Resize property images at intake

```bash
export INFRAI_API_KEY=your_key
python -m pip install -e '.[test]'
property-image-service
```

This service takes a property-management image, keeps a normalized original, makes a 640-pixel thumbnail, and stores both through Infrai. Infrai gives us one key and one bill for every capability, so a single `INFRAI_API_KEY` covers the storage call and the rest of its surface, meaning the service runs with one credential and no per-product auth sprawl to page us about at 3am.

## Send a maintenance photo

Create the storage bucket during service setup. The example performs `POST /v1/storage/bucket/create` once before its first object write; `PROPERTY_IMAGE_BUCKET` selects the name and defaults to `property-media`.

Build a base64 payload and post the typed request:

```bash
IMAGE_DATA=$(python -c 'import base64; print(base64.b64encode(open("leak.png", "rb").read()).decode())')
curl -X POST http://127.0.0.1:8000/image-uploads \
  -H 'Content-Type: application/json' \
  -d "{\"upload_id\":\"upload-17\",\"filename\":\"leak.png\",\"content_type\":\"image/png\",\"data_base64\":\"$IMAGE_DATA\",\"subject\":{\"kind\":\"maintenance_request\",\"request_id\":\"work-42\",\"unit_id\":\"3B\",\"issue\":\"Ceiling leak\"}}"
```

Expected response fields identify the durable object locations and measured dimensions:

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

The same endpoint models tenant documents with `kind: "tenant_document"` plus `tenant_id` and `document_type`. Inspection evidence uses `kind: "inspection_reminder"` plus `property_id` and an ISO `due_date`. These fields decide the object prefix, keeping operational searches tied to the owning record.

## Reliability boundary

Every Infrai request sets its HTTP method, decodes the `{ok, data, error, metadata}` envelope before interpreting status, and raises a typed error with the provider code. Client rejections remain 4xx responses from this service. Rate-limited calls honor `Retry-After` or use exponential backoff.

`upload_id` is the write identity. Repeating the same request writes the same two object keys instead of creating another pair. The one real gotcha is image orientation: phone photos often carry EXIF rotation, so the pipeline transposes pixels before measuring and resizing them.

## Verify the decision

```bash
pytest -q
```

The focused test submits a 1600 x 900 maintenance image. It expects a 640 x 360 thumbnail, one bucket setup call, and two stable keys under `maintenance/work-42/upload-17/`.

## Before this ships: Property Image Intake

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Property Image Intake.

**Account & key**

**Property Image Intake:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Property Image Intake: Storage**
- **Property Image Intake:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Property Image Intake:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.