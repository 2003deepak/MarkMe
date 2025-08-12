import asyncio
import aio_pika
import json
import base64
import numpy as np
import cv2
import faiss
from pymongo import MongoClient
from insightface.app import FaceAnalysis
from app.core.database import init_db
from app.schemas.student import Student
import logging
from app.core.rabbitmq_config import settings
from app.utils.redis_pub_sub import publish_to_channel

# Initialize ArcFace Model
face_app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])  # use CUDAExecutionProvider for GPU
face_app.prepare(ctx_id=0)  # set to -1 for CPU only

EMBEDDING_DIM = 512  # Matches the 512-dimensional face_embedding

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def face_worker():
    logger.info("🚀 Initializing DB connection...")
    await init_db()
    logger.info("✅ Database connected.")

    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()

    queue = await channel.declare_queue(
        "face_recog_queue",  # The same name used in send_to_queue()
        durable=True,
        arguments={"x-max-priority": 10}
    )

    logger.info("[face_worker] Listening on queue: face_recog_queue")

    async with queue.iterator() as messages:
        async for message in messages:
            async with message.process():
                try:
                    payload = json.loads(message.body)
                    data = payload.get("data", {})

                    attendance_id = data.get("attendance_id")
                    image_base64 = data.get("image_base64")
                    semester = data.get("semester")
                    department = data.get("department")
                    program = data.get("program")

                    if not all([image_base64, semester, department, program]):
                        logger.error(f"[face_worker] Missing required data: {data}")
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": "Missing required data"
                        })
                        continue

                    logger.info(f"[face_worker] Processing recognition for semester: {semester}, department: {department}, program: {program}")

                    # Convert semester to int if it's a string, to match DB
                    try:
                        semester = int(semester)
                    except (ValueError, TypeError):
                        logger.warning(f"[face_worker] Invalid semester format: {semester}, keeping as is")

                    # 1️⃣ Decode image
                    image_bytes = base64.b64decode(image_base64)
                    nparr = np.frombuffer(image_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is None:
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": "Invalid image"
                        })
                        continue

                    # 2️⃣ Detect faces
                    faces = face_app.get(img)
                    if not faces:
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": "No faces detected"
                        })
                        continue

                    await publish_to_channel(f"face_progress:{attendance_id}", {
                        "status": "progress",
                        "message": f"{len(faces)} faces detected"
                    })

                    # 3️⃣ Fetch student embeddings
                    student_query = Student.find({
                        "semester": semester,
                        "department": department,
                        "program": program
                    })
                    student_docs = [doc async for doc in student_query]  # Async iteration over FindMany

                    logger.info(f"[face_worker] Fetched {len(student_docs)} students for filters: semester={semester}, department={department}, program={program}")

                    if not student_docs:
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": f"No students found for filters: semester={semester}, department={department}, program={program}"
                        })
                        continue

                    # Extract embeddings, names, and roll numbers
                    student_embeddings = np.array([doc.face_embedding for doc in student_docs], dtype="float32")
                    student_names = [f"{doc.first_name} {doc.last_name}".strip() for doc in student_docs]
                    student_rolls = [doc.roll_number for doc in student_docs]  # Assuming roll_number exists in Student schema

                    # Validate embeddings
                    if student_embeddings.shape[1] != EMBEDDING_DIM:
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": f"Invalid embedding dimension: expected {EMBEDDING_DIM}, got {student_embeddings.shape[1]}"
                        })
                        continue

                    logger.info(f"[face_worker] Loaded {len(student_embeddings)} embeddings with shape {student_embeddings.shape}")

                    # 4️⃣ Prepare FAISS index
                    faiss.normalize_L2(student_embeddings)
                    index = faiss.IndexFlatIP(EMBEDDING_DIM)
                    index.add(student_embeddings)

                    # 5️⃣ Match each face and annotate image
                    results = []
                    for idx, face in enumerate(faces):
                        emb = face.embedding.reshape(1, -1).astype("float32")
                        faiss.normalize_L2(emb)
                        D, I = index.search(emb, 1)
                        sim_score = float(D[0][0])
                        match_idx = int(I[0][0])

                        bbox = face.bbox.astype(int)
                        x1, y1, x2, y2 = bbox
                        confidence = round(sim_score * 100, 2)

                        if sim_score > 0.65:
                            name = student_names[match_idx]
                            roll = student_rolls[match_idx]
                            label = f"{name} ({confidence}%)"
                            color = (0, 255, 0)  # Green for known
                            logger.info(f"[face_worker] Found {name} with roll {roll} and confidence = {confidence:.2f}")
                        else:
                            name = "Unknown"
                            roll = "N/A"
                            label = "Unknown"
                            color = (0, 0, 255)  # Red for unknown
                            # logger.info(f"[face_worker] Unknown face detected")

                        # Annotate the image
                        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                        # Collect result for publishing
                        result = {
                            "status": "progress",
                            "recognized": [
                                {
                                    "roll": roll,
                                    "name": name
                                }
                            ]
                        }
                        results.append(result)

                        # Publish result chunk
                        await publish_to_channel(f"face_progress:{attendance_id}", result)

                    # 6️⃣ Encode annotated image
                    _, buffer = cv2.imencode('.jpg', img)
                    annotated_image_base64 = base64.b64encode(buffer).decode('utf-8')

                    # 7️⃣ Completion with annotated image
                    await publish_to_channel(f"face_progress:{attendance_id}", {
                        "status": "complete",
                        "results": results,
                        "annotated_image": annotated_image_base64
                    })

                except Exception as e:
                    logger.error(f"[face_worker] Error: {str(e)}")
                    await publish_to_channel(f"face_progress:{attendance_id}", {
                        "status": "failed",
                        "reason": f"Error: {str(e)}"
                    })

if __name__ == "__main__":
    asyncio.run(face_worker())