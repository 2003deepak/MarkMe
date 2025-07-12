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

        upload = imagekit.upload_file(
            file=file,
            file_name=filename,
            options=UploadFileRequestOptions(
                folder=f"/{folder}",
                is_private_file=False,
                tags=["profile", "student"]
            )
        )

        if not hasattr(upload, "response_metadata"):
            raise Exception("No response metadata from ImageKit")

        metadata = upload.response_metadata.raw

        if not metadata.get("url") or not metadata.get("fileId"):
            raise Exception(f"Upload failed: {metadata.get('message', 'Unknown error')}")

        return {
            "url": metadata["url"],
            "fileId": metadata["fileId"]
        }

    except Exception as e:
        print(f"ImageKit upload error: {str(e)}")
        raise


async def delete_file(file_id: str):
    try:
        # Step 2: Delete the file using file_id
        delete_response = imagekit.delete_file(file_id=file_id)

        return {"status": "success", "message": f"File with ID {file_id} deleted successfully"}

    except Exception as e:
        print(f"ImageKit delete error: {str(e)}")
        raise