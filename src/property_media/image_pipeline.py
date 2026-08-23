from __future__ import annotations

import base64
import binascii
import io
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal, Protocol

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator


class MaintenanceRequest(BaseModel):
    kind: Literal["maintenance_request"]
    request_id: str = Field(min_length=1, max_length=80)
    unit_id: str = Field(min_length=1, max_length=80)
    issue: str = Field(min_length=1, max_length=500)


class TenantDocument(BaseModel):
    kind: Literal["tenant_document"]
    tenant_id: str = Field(min_length=1, max_length=80)
    document_type: Literal["lease", "identity", "insurance"]


class InspectionReminder(BaseModel):
    kind: Literal["inspection_reminder"]
    property_id: str = Field(min_length=1, max_length=80)
    due_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


Subject = MaintenanceRequest | TenantDocument | InspectionReminder


class ImageUploadRequest(BaseModel):
    upload_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    filename: str = Field(min_length=1, max_length=180)
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    data_base64: str = Field(min_length=1)
    subject: Subject = Field(discriminator="kind")

    @field_validator("filename")
    @classmethod
    def reject_path_names(cls, value: str) -> str:
        if PurePosixPath(value).name != value or "\\" in value:
            raise ValueError("filename must not contain a path")
        return value


class StoredImage(BaseModel):
    bucket: str
    original_key: str
    thumbnail_key: str
    original_width: int
    original_height: int
    thumbnail_width: int
    thumbnail_height: int
    subject_kind: str
    subject_id: str


class ObjectStore(Protocol):
    def create_bucket(self, name: str) -> dict[str, object]:
        raise AssertionError("ObjectStore protocol method")

    def put_object(
        self,
        bucket: str,
        key: str,
        *,
        data_base64: str,
        content_type: str,
    ) -> dict[str, object]:
        raise AssertionError("ObjectStore protocol method")


@dataclass(frozen=True)
class EncodedImage:
    payload: str
    width: int
    height: int


class PropertyImagePipeline:
    def __init__(self, store: ObjectStore, bucket: str, thumbnail_max_edge: int = 640) -> None:
        self._store = store
        self._bucket = bucket
        self._thumbnail_max_edge = thumbnail_max_edge
        self._bucket_ready = False

    def process(self, request: ImageUploadRequest) -> StoredImage:
        raw = self._decode(request.data_base64)
        original, thumbnail = self._render(raw, request.content_type)
        subject_kind, subject_id = self._subject_path(request.subject)
        extension = self._extension(request.content_type)
        prefix = f"{subject_kind}/{subject_id}/{request.upload_id}"
        original_key = f"{prefix}/original.{extension}"
        thumbnail_key = f"{prefix}/thumbnail.{extension}"

        self._ensure_bucket()
        self._store.put_object(
            self._bucket,
            original_key,
            data_base64=original.payload,
            content_type=request.content_type,
        )
        self._store.put_object(
            self._bucket,
            thumbnail_key,
            data_base64=thumbnail.payload,
            content_type=request.content_type,
        )
        return StoredImage(
            bucket=self._bucket,
            original_key=original_key,
            thumbnail_key=thumbnail_key,
            original_width=original.width,
            original_height=original.height,
            thumbnail_width=thumbnail.width,
            thumbnail_height=thumbnail.height,
            subject_kind=subject_kind,
            subject_id=subject_id,
        )

    def _ensure_bucket(self) -> None:
        if not self._bucket_ready:
            self._store.create_bucket(self._bucket)
            self._bucket_ready = True

    def _render(self, raw: bytes, content_type: str) -> tuple[EncodedImage, EncodedImage]:
        try:
            with Image.open(io.BytesIO(raw)) as opened:
                image = ImageOps.exif_transpose(opened)
                image.load()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("data_base64 must contain a supported image") from exc

        output_format = self._format(content_type)
        if output_format == "JPEG" and image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        original = self._encode(image, output_format)
        thumb = image.copy()
        thumb.thumbnail((self._thumbnail_max_edge, self._thumbnail_max_edge), Image.Resampling.LANCZOS)
        return original, self._encode(thumb, output_format)

    @staticmethod
    def _decode(payload: str) -> bytes:
        try:
            return base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("data_base64 is not valid base64") from exc

    @staticmethod
    def _encode(image: Image.Image, output_format: str) -> EncodedImage:
        target = io.BytesIO()
        image.save(target, format=output_format, quality=85, optimize=True)
        return EncodedImage(
            payload=base64.b64encode(target.getvalue()).decode("ascii"),
            width=image.width,
            height=image.height,
        )

    @staticmethod
    def _subject_path(subject: Subject) -> tuple[str, str]:
        if isinstance(subject, MaintenanceRequest):
            return "maintenance", subject.request_id
        if isinstance(subject, TenantDocument):
            return "tenant-documents", subject.tenant_id
        return "inspection-reminders", subject.property_id

    @staticmethod
    def _extension(content_type: str) -> str:
        return {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[content_type]

    @staticmethod
    def _format(content_type: str) -> str:
        return {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[content_type]
