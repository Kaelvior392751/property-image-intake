import base64
import io

from PIL import Image

from property_media.image_pipeline import ImageUploadRequest, PropertyImagePipeline


class RecordingStore:
    def __init__(self) -> None:
        self.buckets: list[str] = []
        self.objects: list[tuple[str, str, str, str]] = []

    def create_bucket(self, name: str) -> dict[str, object]:
        self.buckets.append(name)
        return {"name": name}

    def put_object(
        self,
        bucket: str,
        key: str,
        *,
        data_base64: str,
        content_type: str,
    ) -> dict[str, object]:
        self.objects.append((bucket, key, data_base64, content_type))
        return {"key": key}


def png_payload(width: int, height: int) -> str:
    output = io.BytesIO()
    Image.new("RGB", (width, height), color=(30, 90, 140)).save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def test_maintenance_photo_is_resized_and_stored_under_stable_keys() -> None:
    store = RecordingStore()
    pipeline = PropertyImagePipeline(store, bucket="property-media", thumbnail_max_edge=640)
    request = ImageUploadRequest.model_validate(
        {
            "upload_id": "upload-17",
            "filename": "leaking-ceiling.png",
            "content_type": "image/png",
            "data_base64": png_payload(1600, 900),
            "subject": {
                "kind": "maintenance_request",
                "request_id": "work-42",
                "unit_id": "3B",
                "issue": "Ceiling leak above the kitchen window",
            },
        }
    )

    result = pipeline.process(request)

    assert store.buckets == ["property-media"]
    assert [item[1] for item in store.objects] == [
        "maintenance/work-42/upload-17/original.png",
        "maintenance/work-42/upload-17/thumbnail.png",
    ]
    assert (result.original_width, result.original_height) == (1600, 900)
    assert (result.thumbnail_width, result.thumbnail_height) == (640, 360)

    thumbnail_bytes = base64.b64decode(store.objects[1][2])
    with Image.open(io.BytesIO(thumbnail_bytes)) as thumbnail:
        assert thumbnail.size == (640, 360)

