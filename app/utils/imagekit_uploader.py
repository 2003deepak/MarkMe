#imagekit uploader

import base64
from imagekitio import ImageKit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
from app.core.config import settings


imagekit = ImageKit(
    public_key=settings.IMAGEKIT_PUBLIC_KEY,
    private_key=settings.IMAGEKIT_PRIVATE_KEY,
    url_endpoint=settings.IMAGEKIT_URL_ENDPOINT
)


async def upload_file_to_imagekit(
    file: bytes,
    filename: str,
    folder: str,
    tags: list = None
):
    try:
        # convert to base64 to avoid file corruption
        encoded_file = base64.b64encode(file).decode("utf-8")

        upload = imagekit.upload_file(
            file=encoded_file,
            file_name=filename,
            options=UploadFileRequestOptions(
                folder=f"/{folder}",
                use_unique_file_name=False,
                tags=tags or []
            )
        )

        metadata = upload.response_metadata.raw

        return {
            "url": metadata["url"],
            "fileId": metadata["fileId"]
        }

    except Exception as e:
        print(f"[ImageKit Upload Error]: {str(e)}")
        raise


async def delete_file(file_id: str):
    try:
        imagekit.delete_file(file_id=file_id)
        return {"status": "success"}
    except Exception as e:
        print(f"[ImageKit Delete Error]: {str(e)}")
        raise