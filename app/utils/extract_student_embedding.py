import cv2
import numpy as np
from fastapi import HTTPException
from insightface.app import FaceAnalysis
from typing import List
from pathlib import Path

# init model
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

        # validate path
        if not path_obj.exists() or path_obj.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            print(f"Skipping invalid path: {path}")
            continue

        img = cv2.imread(str(path_obj))
        if img is None:
            print(f"Skipping unreadable image: {path}")
            continue

        # improve detection (important)
        img = cv2.resize(img, None, fx=1.3, fy=1.3)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        faces = face_app.get(img)

        if not faces:
            print(f"Skipping image (no face detected): {path}")
            continue

        # pick largest face
        largest_face = max(
            faces,
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
        )

        # filter small faces
        x1, y1, x2, y2 = largest_face.bbox.astype(int)
        face_area = (x2 - x1) * (y2 - y1)

        if face_area < 5000:
            print(f"Skipping small face: {path}")
            continue

        emb = largest_face.embedding.astype("float32")

        # normalize embedding
        emb = emb / np.linalg.norm(emb)

        embeddings.append(emb)

    # ---------------- VALIDATION ----------------

    if len(embeddings) < 2:
        raise ValueError("Not enough valid face images. Please upload clearer images.")

    # ---------------- CONSISTENCY FILTER ----------------

    valid_embeddings = []

    for i, emb in enumerate(embeddings):
        similarities = []

        for j, other in enumerate(embeddings):
            if i == j:
                continue
            sim = np.dot(emb, other)
            similarities.append(sim)

        avg_sim = np.mean(similarities)

        print(f"Image {i} avg similarity: {avg_sim:.3f}")

        # relaxed threshold for real-world data
        if avg_sim >= 0.35:
            valid_embeddings.append(emb)
        else:
            print(f"Dropping outlier image {i}")

    if len(valid_embeddings) < 2:
        raise ValueError("Face images are inconsistent. Please upload similar face images.")

    # ---------------- FINAL EMBEDDING ----------------

    avg_embedding = np.mean(valid_embeddings, axis=0)

    # normalize again
    avg_embedding = avg_embedding / np.linalg.norm(avg_embedding)

    if avg_embedding.shape != (EMBEDDING_DIM,):
        raise ValueError(f"Generated embedding has incorrect dimension: {avg_embedding.shape}")

    return avg_embedding.astype("float32")