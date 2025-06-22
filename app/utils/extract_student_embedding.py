import cv2
import numpy as np
from fastapi import UploadFile, HTTPException
from insightface.app import FaceAnalysis
from typing import List
from pathlib import Path

# Initialize ArcFace Model
face_app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
face_app.prepare(ctx_id=0)  # set to -1 for CPU only
EMBEDDING_DIM = 512

async def extract_student_embedding(image_paths: List[str]) -> np.ndarray:
    """Extract average face embedding from a list of uploaded images."""
    # Validate number of images
    if len(image_paths) < 3 or len(image_paths) > 4:
        raise HTTPException(
            status_code=400,
            detail="Please upload exactly 3 to 4 images"
        )

    embeddings = []
    valid_extensions = {".jpg", ".jpeg", ".png"}
    max_file_size = 5 * 1024 * 1024  # 5 MB

    for path in image_paths:
        path_obj = Path(path)
        if not path_obj.exists() or path_obj.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            raise ValueError(f"Invalid image path: {path}")
        
        img = cv2.imread(str(path_obj))
        if img is None:
            raise ValueError(f"Failed to load image: {path}")

        faces = face_app.get(img)
        if not faces:
            raise ValueError(f"No face detected in image: {path}")
        
        embeddings.append(faces[0].embedding)

    avg_embedding = np.mean(embeddings, axis=0)
    if avg_embedding.shape != (EMBEDDING_DIM,):
        raise ValueError(f"Generated embedding has incorrect dimension: {avg_embedding.shape}")
    
    return avg_embedding.astype("float32")