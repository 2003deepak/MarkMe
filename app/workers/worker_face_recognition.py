import asyncio
import aio_pika
import json
from app.utils.imagekit_uploader import upload_file_to_imagekit
import uuid
import base64
import numpy as np
import cv2
import faiss
from app.models.allModel import StudentProjection
from app.schemas.student import Student
from app.core.database import init_db
from insightface.app import FaceAnalysis
from app.core.rabbitmq_config import settings
from app.core.redis import redis_client
from app.utils.redis_pub_sub import publish_to_channel
from app.core.faiss_cache import faiss_cache, get_cache_key
import onnxruntime as ort
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# GPU / CPU auto selection
available_providers = ort.get_available_providers()
if "CUDAExecutionProvider" in available_providers:
    providers = ["CUDAExecutionProvider"]
    ctx_id = 0
    logger.info("Using GPU")
else:
    providers = ["CPUExecutionProvider"]
    ctx_id = -1
    logger.warning("Using CPU")



async def connect_rabbitmq():
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            logger.info("✅ Connected to RabbitMQ")
            return connection
        except Exception as e:
            logger.warning(f"RabbitMQ not ready, retrying... {e}")
            await asyncio.sleep(5)
            
# lock for cache build
faiss_locks = {}

# Initialize ArcFace Model
face_app = FaceAnalysis(name='buffalo_l', providers=providers)
face_app.prepare(ctx_id=ctx_id)
logger.info("[face_worker] Initialized ArcFace model with providers: %s", providers)

EMBEDDING_DIM = 512

# =========================
# LOAD STUDENTS + FAISS CACHE
# =========================
async def load_student_data(semester, department, program):

    cache_key = get_cache_key(semester, department, program)

    # return cache
    if cache_key in faiss_cache:
        logger.info(f"Using cached FAISS for {cache_key}")
        return faiss_cache[cache_key]

    lock = faiss_locks.setdefault(cache_key, asyncio.Lock())

    async with lock:

        if cache_key in faiss_cache:
            return faiss_cache[cache_key]

        logger.info(f"Building FAISS index for {cache_key}")

        query_filters = {
            "semester": semester,
            "department": department,
            "program": program
        }

        student_docs = await Student.find(query_filters).project(StudentProjection).to_list()

        if not student_docs:
            return None

        valid_students = [
            doc for doc in student_docs
            if doc.face_embedding and len(doc.face_embedding) == EMBEDDING_DIM
        ]

        if not valid_students:
            return None

        embeddings = np.array(
            [doc.face_embedding for doc in valid_students],
            dtype="float32"
        )

        faiss.normalize_L2(embeddings)

        index = faiss.IndexFlatIP(EMBEDDING_DIM)
        index.add(embeddings)
        
        # 🔥 9. ADD FAISS INDEX LOG
        logger.info(
            "[FAISS] vectors=%d dim=%d",
            index.ntotal,
            EMBEDDING_DIM
        )

        data = {
            "index": index,
            "names": [f"{doc.first_name} {doc.last_name}" for doc in valid_students],
            "rolls": [doc.roll_number for doc in valid_students],
            "ids": [str(doc.id) for doc in valid_students],
            "docs": valid_students
        }

        faiss_cache[cache_key] = data
        
        MAX_CACHE = 10

        if len(faiss_cache) > MAX_CACHE:
            faiss_cache.pop(next(iter(faiss_cache)))
            logger.info(f"Cached FAISS for {cache_key}")

        return data

async def process_single_image(
    img, current_image, student_data, recognized_set_key, attendance_id, recognized_ids
):
    """Process a single image and return results"""
    logger.debug("[face_worker] Processing image %d for attendance_id: %s", current_image, attendance_id)
    
    # Detect faces
    raw_faces = face_app.get(img)
    if not raw_faces:
        return [], img, 0

    faces = sorted(
        raw_faces,
        key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]),
        reverse=True
    )
    
    logger.info("[face_worker] Detected %d faces in image %d", len(faces), current_image)
    
    # Extract student data
    student_names = student_data['names']
    student_rolls = student_data['rolls']
    student_ids = student_data['ids']
    index = student_data['index']
    
    image_results = []
    new_recognitions = 0
    
    # Process each face
    for idx, face in enumerate(faces):
        logger.debug("[face_worker] Processing face %d/%d in image %d", idx + 1, len(faces), current_image)
        
        # 🔥 5. ADD FACE SIZE FILTER
        bbox = face.bbox.astype(int)
        x1, y1, x2, y2 = bbox
        face_area = (x2 - x1) * (y2 - y1)
        
        if face_area < 5000:
            logger.warning(
                "[SKIP] Small face img=%d face=%d area=%d",
                current_image,
                idx + 1,
                face_area
            )
            continue
        
        # Get face embedding
        emb = face.embedding.reshape(1, -1).astype("float32")
        faiss.normalize_L2(emb)
        
        # 🔥 8. ADD EMBEDDING HEALTH LOG
        logger.debug(
            "[EMB] min=%.3f max=%.3f mean=%.3f",
            float(emb.min()),
            float(emb.max()),
            float(emb.mean())
        )
        
        # 🔥 1. CHANGE FAISS SEARCH → TOP 3
        D, I = index.search(emb, 3)
        
        # 🔥 2. ADD TOP-3 LOGGING
        logger.info(
            "[TOP3] img=%d face=%d scores=%s",
            current_image,
            idx + 1,
            [round(float(x), 4) for x in D[0]]
        )
        
        sim_score = float(D[0][0])
        match_idx = int(I[0][0])
        confidence = round(sim_score * 100, 2)
        
        # 🔥 3. ADD MATCH DEBUG
        logger.info(
            "[MATCH] img=%d face=%d sim=%.4f conf=%.2f student=%s",
            current_image,
            idx + 1,
            sim_score,
            confidence,
            student_ids[match_idx] if match_idx < len(student_ids) else "INVALID"
        )
        
        # 🔥 7. FIX THRESHOLD (TEMPORARY BUT NEEDED)
        if sim_score > 0.45:  # Recognition threshold (changed from 0.60 to 0.45)
            student_id = student_ids[match_idx]
            name = student_names[match_idx]
            roll = student_rolls[match_idx]
            
            logger.debug("[face_worker] Potential match - Student ID: %s, Name: %s, Roll: %s", 
                        student_id, name, roll)
            
            if student_id not in recognized_ids:
                recognized_ids.add(student_id)
                await redis_client.sadd(recognized_set_key, student_id)

                label = f"{name} ({confidence}%)"
                color = (0, 255, 0)
                new_recognitions += 1

                await publish_to_channel(f"student_recognized:{attendance_id}", {
                    "student_id": student_id,
                    "name": name,
                    "roll_number": roll,
                    "confidence": confidence,
                    "image_index": current_image
                })

            else:
                label = f"{name} - Duplicate ({confidence}%)"
                color = (255, 255, 0)
                
            # Add to results regardless of duplicate status
            result = {
                "roll": roll,
                "name": name,
                "confidence": confidence,
                "image_index": current_image,
                "student_id": student_id,
                "is_duplicate": student_id in recognized_ids
            }
            image_results.append(result)
            
        else:
            # Unknown face
            label = f"Unknown ({confidence}%)"
            color = (0, 0, 255)  # Red for unknown
            logger.debug("[face_worker] ❓ Unknown face %d in image %d (confidence=%.1f%%)", 
                        idx + 1, current_image, confidence)
            
            result = {
                "roll": "N/A",
                "name": "Unknown",
                "confidence": confidence,
                "image_index": current_image,
                "student_id": None,
                "is_duplicate": False
            }
            image_results.append(result)
        
        # Annotate image
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.putText(img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    
    logger.debug("[face_worker] Image %d processing complete: %d results, %d new recognitions", 
                current_image, len(image_results), new_recognitions)
    return image_results, img, new_recognitions

async def face_worker():
    logger.info("[face_worker] 🚀 Starting face recognition worker")
    logger.info("[face_worker] Initializing DB connection...")
    await init_db()
    logger.info("[face_worker] ✅ Database connected successfully")

    logger.debug("[face_worker] Connecting to RabbitMQ: %s", settings.rabbitmq_url)
    connection = await connect_rabbitmq()
    channel = await connection.channel()
    logger.info("[face_worker] ✅ RabbitMQ connection and channel established")

    queue = await channel.declare_queue(
        "face_recog_queue",
        durable=True,
        arguments={"x-max-priority": 10}
    )
    logger.info("[face_worker] 👂 Listening on queue: face_recog_queue")

    async with queue.iterator() as messages:
        
        async for message in messages:
            
            recognized_ids = set()
            
            async with message.process():
                logger.info("[face_worker] 📨 Received message from queue")
                student_data = None  # Initialize for cleanup
                recognized_set_key = None
                all_annotated_images = []  # Initialize early to avoid undefined errors
                attendance_id = None  # Initialize attendance_id
                
                try:
                    payload = json.loads(message.body)
                    data = payload.get("data", {})
                    logger.debug("[face_worker] 📋 Parsed payload data keys: %s", list(data.keys()))

                    # Extract job parameters
                    attendance_id = data.get("attendance_id")
                    image_base64_list = data.get("image_base64_list", [])
                    num_images = len(image_base64_list)
                    semester = data.get("semester")
                    department = data.get("department")
                    program = data.get("program")


                    # Validate required data
                    if not all([attendance_id, image_base64_list, semester, department, program]):
                        logger.error("[face_worker] ❌ Missing required data for attendance_id: %s", attendance_id)
                        missing_fields = []
                        if not attendance_id: missing_fields.append("attendance_id")
                        if not image_base64_list: missing_fields.append("image_base64_list")
                        if not semester: missing_fields.append("semester")
                        if not department: missing_fields.append("department")
                        if not program: missing_fields.append("program")
                        
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": f"Missing required data: {', '.join(missing_fields)}"
                        })
                        continue

                    # Convert semester to int
                    try:
                        semester = int(semester)
                        logger.debug("[face_worker] ✅ Converted semester to int: %d", semester)
                    except (ValueError, TypeError) as e:
                        logger.error("[face_worker] ❌ Invalid semester format: %s, error: %s", semester, str(e))
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": f"Invalid semester format: {semester}"
                        })
                        continue

                    # Initialize Redis set for unique students
                    recognized_set_key = f"recognized_students:{attendance_id}"
                    await redis_client.delete(recognized_set_key)
                    logger.info("[face_worker] 🔧 Initialized Redis set: %s", recognized_set_key)

                    # Load student data once for the entire job
                    logger.info("[face_worker] 📥 Loading student data...")
                    student_data = await load_student_data(semester, department, program)
                    if not student_data:
                        logger.error("[face_worker] ❌ No student data loaded")
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": f"No students with valid face embeddings found for the given criteria"
                        })
                        continue

                    logger.info("[face_worker] ✅ Loaded %d students for recognition", len(student_data['ids']))

                    # Process each image
                    total_faces = 0
                    total_new_recognitions = 0

                    for current_image, image_base64 in enumerate(image_base64_list, 1):
                        logger.info("[face_worker] 🖼️ Processing image %d/%d", current_image, num_images)

                        try:
                            # Decode image
                            logger.debug("[face_worker] 🔍 Decoding image %d", current_image)
                            image_bytes = base64.b64decode(image_base64)
                            nparr = np.frombuffer(image_bytes, np.uint8)
                            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            
                            if img is None:
                                logger.warning("[face_worker] ❌ Failed to decode image %d", current_image)
                                # Store placeholder for failed image
                                all_annotated_images.append({
                                    "image_index": current_image,
                                    "status": "failed",
                                    "message": "Failed to decode image",
                                    "annotated_image_base64": None
                                })
                                await publish_to_channel(f"face_progress:{attendance_id}", {
                                    "status": "progress",
                                    "current_image": current_image,
                                    "total_images": num_images,
                                    "message": f"Failed to decode image {current_image}",
                                    "recognized_count": len(recognized_ids)
                                })
                                continue

                            # 🔥 4. ADD IMAGE QUALITY LOG
                            h, w, _ = img.shape
                            logger.info(
                                "[IMG] idx=%d shape=%s brightness=%.2f",
                                current_image,
                                (h, w),
                                float(np.mean(img))
                            )
                            
                            # 🔥 6. ADD IMAGE PREPROCESSING
                            # improve brightness
                            img = cv2.convertScaleAbs(img, alpha=1.2, beta=20)
                            # denoise
                            img = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
                            
                            logger.debug("[face_worker] ✅ Image %d decoded successfully, shape: %s", 
                                       current_image, str(img.shape))

                            # Process the image
                            logger.debug("[face_worker] 🔍 Running face detection on image %d", current_image)
                            image_results, annotated_img, new_recognitions = await process_single_image(
                                img,
                                current_image,
                                student_data,
                                recognized_set_key,
                                attendance_id,
                                recognized_ids
                            )

                            # Always encode and store the annotated image (even if no faces detected)
                            _, buffer = cv2.imencode('.jpg', annotated_img)
                            image_bytes = buffer.tobytes()
                            
                            #upload to imagekit
                            filename = f"attendance_{attendance_id}_{current_image}_{uuid.uuid4().hex}.jpg"
                            
                            upload_result = await upload_file_to_imagekit(
                                file=image_bytes,
                                filename=filename,
                                folder="attendance_faces",
                                tags=["attendance", str(attendance_id)]
                            )

                            annotated_image_url = upload_result["url"]

                            # Store annotated image info
                            annotated_image_info = {
                                "image_index": current_image,
                                "status": "processed",
                                "faces_detected": len(image_results),
                                "new_recognitions": new_recognitions,
                                "annotated_image_url": annotated_image_url,
                                "message": f"Processed {len(image_results)} faces, {new_recognitions} new recognitions"
                            }
                            all_annotated_images.append(annotated_image_info)

                            if not image_results:
                                # No faces detected but still store the annotated image
                                recognized_count = len(recognized_ids)
                                await publish_to_channel(f"face_progress:{attendance_id}", {
                                    "status": "progress",
                                    "current_image": current_image,
                                    "total_images": num_images,
                                    "recognized_count": recognized_count,
                                    "annotated_image_url": annotated_image_url,
                                    "message": f"No faces detected in image {current_image}"
                                })
                            else:
                                # Update counters
                                total_faces += len(image_results)
                                total_new_recognitions += new_recognitions

                                # Get current recognition count
                                recognized_count = len(recognized_ids)

                                # Publish progress
                                await publish_to_channel(f"face_progress:{attendance_id}", {
                                    "status": "image_processed",
                                    "current_image": current_image,
                                    "total_images": num_images,
                                    "faces_in_image": len(image_results),
                                    "new_recognitions_in_image": new_recognitions,
                                    "total_recognized_count": recognized_count,
                                    "annotated_image_url": annotated_image_url,
                                    "message": f"Processed image {current_image}: {len(image_results)} faces, {new_recognitions} new recognitions"
                                })

                                logger.info("[face_worker] ✅ Image %d processed: %d faces, %d new recognitions, total unique: %d", 
                                           current_image, len(image_results), new_recognitions, recognized_count)

                        except Exception as e:
                            logger.error("[face_worker] ❌ Error processing image %d: %s", current_image, str(e))
                            # Store error info for this image
                            all_annotated_images.append({
                                "image_index": current_image,
                                "status": "error",
                                "message": str(e),
                                "annotated_image_base64": None
                            })
                            await publish_to_channel(f"face_progress:{attendance_id}", {
                                "status": "progress",
                                "current_image": current_image,
                                "total_images": num_images,
                                "message": f"Error processing image {current_image}: {str(e)}",
                                "recognized_count": len(await redis_client.smembers(recognized_set_key))
                            })

                    # Final results compilation
                    logger.info("[face_worker] 📊 Compiling final results...")
                    if len(all_annotated_images) == 0:
                        logger.error("[face_worker] ❌ No images processed successfully for attendance_id: %s", attendance_id)
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": "No images could be processed successfully"
                        })
                    else:
                        # Get final unique students
                        unique_student_ids = list(recognized_ids)
                        
                        logger.info("[face_worker] 🎯 Building final results for %d unique students", len(unique_student_ids))
                        
                        unique_students = []
                        
                        # Build a lookup dictionary from the already loaded student data
                        if student_data:  # Check if student_data exists
                            student_lookup = {str(doc.id): doc for doc in student_data['docs']}
                            logger.debug("[face_worker] Built student lookup with %d entries", len(student_lookup))
                            
                            for student_id in unique_student_ids:
                                try:
                                    logger.debug("[face_worker] Processing student ID: %s", student_id)
                                    # Use the lookup dictionary instead of database query
                                    student = student_lookup.get(student_id)
                                    if student:
                                        # FIX: Use str(student.id) - this is the MongoDB _id
                                        student_info = {
                                            "student_id": str(student.id),  # This is the MongoDB _id
                                            "name": f"{student.first_name} {student.last_name}".strip(),
                                            "roll_number": student.roll_number,
                                            "email": getattr(student, 'email', 'N/A')
                                        }
                                        unique_students.append(student_info)
                                        logger.debug("[face_worker] ✅ Added student to final results: %s (ID: %s)", 
                                                   student_info["name"], student_info["student_id"])
                                    else:
                                        logger.warning("[face_worker] ❌ Student not found in lookup for ID: %s", student_id)
                                except Exception as e:
                                    logger.error("[face_worker] ❌ Error processing student %s: %s", student_id, str(e))
                                    logger.error("[face_worker] Student object attributes: %s", dir(student) if student else "No student object")

                        logger.info("[face_worker] ✅ Final unique students count: %d", len(unique_students))

                        # Send completion message
                        completion_message = {
                            "status": "complete",
                            "recognized_students": unique_students,
                            "total_unique": len(unique_students),
                            "total_faces_detected": total_faces if 'total_faces' in locals() else 0,
                            "images_processed": num_images,
                            "all_annotated_images": all_annotated_images,  # Now guaranteed to be defined
                            "message": f"Recognition complete: {len(unique_students)} unique students from {num_images} images ({total_faces if 'total_faces' in locals() else 0} total faces)"
                        }
                        
                        await publish_to_channel(f"face_progress:{attendance_id}", completion_message)
                        logger.info("[face_worker] 🎉 Job completed - attendance_id: %s, unique students: %d, total faces: %d", 
                                   attendance_id, len(unique_students), total_faces if 'total_faces' in locals() else 0)

                except Exception as e:
                    logger.error("[face_worker] 💥 Unexpected error for attendance_id %s: %s", 
                               attendance_id if attendance_id else 'unknown', str(e))
                    logger.error("[face_worker] Traceback:", exc_info=True)
                    
                    if attendance_id:
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": f"Unexpected error: {str(e)}"
                        })
                
                finally:
                    # Cleanup Redis set
                    if recognized_set_key:
                        try:
                            await redis_client.delete(recognized_set_key)
                            logger.debug("[face_worker] 🧹 Cleaned up Redis set: %s", recognized_set_key)
                        except Exception as e:
                            logger.error("[face_worker] ❌ Error cleaning up Redis set: %s", str(e))
                    
                    logger.info("[face_worker] 🔄 Ready for next message")

if __name__ == "__main__":
    asyncio.run(face_worker())