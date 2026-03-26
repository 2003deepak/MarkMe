import base64
from imagekitio import ImageKit
from app.core.config import settings

# In the latest SDK, only private_key is passed to the constructor
imagekit = ImageKit(
    private_key=settings.IMAGEKIT_PRIVATE_KEY
)

async def upload_file_to_imagekit(file: bytes, filename: str, folder: str, tags: list = None):
    try:
        # Pass raw bytes directly
        response = imagekit.files.upload(
            file=file,
            file_name=filename,
            folder=f"/{folder}",
            use_unique_file_name=True,
            tags=tags or []
        )
        
        return {
            "url": response.url,
            "fileId": response.file_id
        }
    except Exception as e:
        print(f"[ImageKit Upload Error]: {str(e)}")
        raise

async def delete_file(file_id: str):
    try:
        imagekit.files.delete(file_id=file_id)
        return {"status": "success"}
    except Exception as e:
        print(f"[ImageKit Delete Error]: {str(e)}")
        raise