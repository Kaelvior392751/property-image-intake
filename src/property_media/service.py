from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from .image_pipeline import ImageUploadRequest, PropertyImagePipeline, StoredImage
from .infrai_client import InfraiClient, InfraiError


def create_app(client: InfraiClient | None = None) -> FastAPI:
    storage = client or InfraiClient.from_env()
    bucket = os.environ.get("PROPERTY_IMAGE_BUCKET", "property-media")
    pipeline = PropertyImagePipeline(storage, bucket=bucket)
    app = FastAPI(title="Property image intake")

    @app.post("/image-uploads", response_model=StoredImage, status_code=201)
    def upload_image(request: ImageUploadRequest) -> StoredImage:
        try:
            return pipeline.process(request)
        except InfraiError as exc:
            client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
            raise HTTPException(
                status_code=client_status,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app

