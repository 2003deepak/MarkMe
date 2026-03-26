import cv2
import numpy as np
from fastapi import HTTPException
from insightface.app import FaceAnalysis
from typing import List
from pathlib import Path

# Initialize ArcFace Model
face_app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
face_app.prepare(ctx_id=0)

EMBEDDING_DIM = 512


async def extract_student_embedding(image_paths: List[str]) -> np.ndarray:

    if len(image_paths) < 3 or len(image_paths) > 4:
        raise HTTPException(
            status_code=400,
            detail="Please upload exactly 3 to 4 images"
        )

    embeddings = []

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

        # pick largest face (IMPORTANT)
        largest_face = max(
            faces,
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
        )

        # optional: filter very small faces
        x1, y1, x2, y2 = largest_face.bbox.astype(int)
        face_area = (x2 - x1) * (y2 - y1)

        if face_area < 5000:
            raise ValueError(f"Face too small in image: {path}")

        emb = largest_face.embedding.astype("float32")

        # normalize BEFORE averaging (VERY IMPORTANT)
        emb = emb / np.linalg.norm(emb)

        embeddings.append(emb)

    # consistency check (advanced)
    base = embeddings[0]
    for i, emb in enumerate(embeddings[1:], 1):
        sim = np.dot(base, emb)
        if sim < 0.5:
            raise ValueError(f"Inconsistent face detected across images (image {i})")

    # average embeddings
    avg_embedding = np.mean(embeddings, axis=0)

    # normalize again AFTER averaging
    avg_embedding = avg_embedding / np.linalg.norm(avg_embedding)

    if avg_embedding.shape != (EMBEDDING_DIM,):
        raise ValueError(f"Generated embedding has incorrect dimension: {avg_embedding.shape}")

    return avg_embedding.astype("float32")