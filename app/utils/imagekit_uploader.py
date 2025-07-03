import os
import uuid
from imagekitio import ImageKit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
from app.core.config import settings

# Initialize ImageKit
imagekit = ImageKit(
    public_key=settings.IMAGEKIT_PUBLIC_KEY,
    private_key=settings.IMAGEKIT_PRIVATE_KEY,
    url_endpoint=settings.IMAGEKIT_URL_ENDPOINT
)

async def upload_image_to_imagekit(file: bytes, folder: str):
    try:
        filename = f"{uuid.uuid4().hex}.jpg"

        # Upload file as bytes
        upload = imagekit.upload_file(
            file=file,
            file_name=filename,
            options=UploadFileRequestOptions(
                folder=f"/{folder}",
                is_private_file=False,
                tags=["profile", "student"]
            )
        )

        # Validate upload
        if not hasattr(upload, "response_metadata") or not upload.response_metadata.raw.get("url"):
            raise Exception(f"Image upload to ImageKit failed: {upload.response_metadata.raw.get('message', 'Unknown error')}")

        return upload.response_metadata.raw["url"]

    except Exception as e:
        print(f"ImageKit upload error: {str(e)}")
        raise