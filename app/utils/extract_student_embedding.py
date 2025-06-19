import cv2
import numpy as np
from fastapi import UploadFile, HTTPException
from insightface.app import FaceAnalysis
from typing import List

# Initialize ArcFace Model
face_app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
face_app.prepare(ctx_id=0)  # set to -1 for CPU only
EMBEDDING_DIM = 512

async def extract_student_embedding(images: List[UploadFile]) -> np.ndarray:
    """Extract average face embedding from a list of uploaded images."""
    # Validate number of images
    if len(images) < 3 or len(images) > 4:
        raise HTTPException(
            status_code=400,
            detail="Please upload exactly 3 to 4 images"
        )

    embeddings = []
    valid_extensions = {".jpg", ".jpeg", ".png"}
    max_file_size = 5 * 1024 * 1024  # 5 MB

    for image in images:
        # Validate file extension
        file_ext = f".{image.filename.split('.')[-1].lower()}"
        if file_ext not in valid_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {image.filename}. Only JPG, JPEG, or PNG allowed"
            )

        # Validate file size
        contents = await image.read()
        if len(contents) > max_file_size:
            raise HTTPException(
                status_code=400,
                detail=f"File {image.filename} exceeds 5 MB limit"
            )

        # Convert to OpenCV image
        img_array = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to decode image: {image.filename}"
            )

        # Extract face embedding
        faces = face_app.get(img)
        if not faces:
            raise HTTPException(
                status_code=400,
                detail=f"No faces detected in image: {image.filename}"
            )

        embeddings.append(faces[0].embedding)

    # Compute average embedding
    avg_embedding = np.mean(embeddings, axis=0)
    if avg_embedding.shape != (EMBEDDING_DIM,):
        raise HTTPException(
            status_code=500,
            detail=f"Generated embedding has incorrect dimension: {avg_embedding.shape}"
        )

    return avg_embedding.astype("float32")