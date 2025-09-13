import asyncio
import aio_pika
import json
import base64
import numpy as np
import cv2
import faiss
from app.schemas.student import Student
from app.core.database import init_db
from insightface.app import FaceAnalysis
from app.core.rabbitmq_config import settings
from app.core.redis import redis_client
from app.utils.redis_pub_sub import publish_to_channel
import onnxruntime as ort
import logging

logger = logging.getLogger(__name__)

# Auto-select provider
available_providers = ort.get_available_providers()
if "CUDAExecutionProvider" in available_providers:
    providers = ["CUDAExecutionProvider"]
    ctx_id = 0
    logger.info("✅ Using GPU for face recognition with CUDAExecutionProvider")
else:
    providers = ["CPUExecutionProvider"]
    ctx_id = -1
    logger.warning("⚠️ CUDA not available, falling back to CPUExecutionProvider")

# Initialize ArcFace Model
face_app = FaceAnalysis(name='buffalo_l', providers=providers)
face_app.prepare(ctx_id=ctx_id)
logger.info("[face_worker] Initialized ArcFace model with providers: %s", providers)

EMBEDDING_DIM = 512

async def load_student_data(semester, department, program, academic_year, attendance_id):
    """Load and prepare student data for face recognition"""
    logger.debug("[face_worker] Loading student data for filters: semester=%s, department=%s, program=%s, academic_year=%s", 
                semester, department, program, academic_year)
    
    # Use the same query structure as the working single image version
    query_filters = {
        "semester": semester,
        "department": department,
        "program": program
    }
    
    # Add academic_year filter if provided
    # if academic_year:
    #     query_filters["batch_year"] = academic_year
    
    student_query = Student.find(query_filters)
    student_docs = [doc async for doc in student_query]
    logger.info("[face_worker] Fetched %d students for attendance_id: %s with filters: %s", 
               len(student_docs), attendance_id, query_filters)

    if not student_docs:
        logger.error("[face_worker] No students found for filters: %s", query_filters)
        return None

    # Validate embeddings exist
    valid_students = []
    for doc in student_docs:
        if hasattr(doc, 'face_embedding') and doc.face_embedding is not None:
            if len(doc.face_embedding) == EMBEDDING_DIM:
                valid_students.append(doc)
            else:
                logger.warning("[face_worker] Invalid embedding dimension for student %s: %d", 
                             doc.student_id, len(doc.face_embedding))
        else:
            logger.warning("[face_worker] No face embedding found for student %s", doc.student_id)
    
    if not valid_students:
        logger.error("[face_worker] No students with valid embeddings found")
        return None
    
    logger.info("[face_worker] Found %d students with valid embeddings", len(valid_students))
    
    # Prepare data arrays
    student_embeddings = np.array([doc.face_embedding for doc in valid_students], dtype="float32")
    student_names = [f"{doc.first_name} {doc.last_name}".strip() for doc in valid_students]
    student_rolls = [doc.roll_number for doc in valid_students]
    student_ids = [str(doc.student_id) for doc in valid_students]  # Ensure string format
    
    # Normalize embeddings and create FAISS index
    faiss.normalize_L2(student_embeddings)
    index = faiss.IndexFlatIP(EMBEDDING_DIM)
    index.add(student_embeddings)
    logger.info("[face_worker] Built FAISS index with %d embeddings", len(student_embeddings))
    
    return {
        'embeddings': student_embeddings,
        'names': student_names,
        'rolls': student_rolls,
        'ids': student_ids,
        'index': index,
        'docs': valid_students
    }

async def process_single_image(img, current_image, student_data, recognized_set_key, attendance_id):
    """Process a single image and return results"""
    logger.debug("[face_worker] Processing image %d for attendance_id: %s", current_image, attendance_id)
    
    # Detect faces
    faces = face_app.get(img)
    if not faces:
        logger.warning("[face_worker] No faces detected in image %d", current_image)
        return [], img, 0
    
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
        
        # Get face embedding
        emb = face.embedding.reshape(1, -1).astype("float32")
        faiss.normalize_L2(emb)
        
        # Search in FAISS index
        D, I = index.search(emb, 1)
        sim_score = float(D[0][0])
        match_idx = int(I[0][0])
        confidence = round(sim_score * 100, 2)
        
        logger.debug("[face_worker] Face %d similarity score: %.3f, confidence: %.1f%%", 
                    idx + 1, sim_score, confidence)
        
        # Get bounding box
        bbox = face.bbox.astype(int)
        x1, y1, x2, y2 = bbox
        
        if sim_score > 0.50:  # Recognition threshold
            student_id = student_ids[match_idx]
            name = student_names[match_idx]
            roll = student_rolls[match_idx]
            
            # Check if student already recognized (handle Redis bytes vs string)
            recognized_members = await redis_client.smembers(recognized_set_key)
            recognized_ids = {member.decode('utf-8') if isinstance(member, bytes) else str(member) 
                            for member in recognized_members}
            
            if student_id not in recognized_ids:
                # New recognition
                await redis_client.sadd(recognized_set_key, student_id)
                label = f"{name} ({confidence}%)"
                color = (0, 255, 0)  # Green for new recognition
                new_recognitions += 1
                logger.info("[face_worker] NEW recognition: %s (roll %s, ID %s) confidence=%.1f%% in image %d", 
                           name, roll, student_id, confidence, current_image)
                
                # Publish individual student recognition immediately
                student_recognition = {
                    "student_id": student_id,
                    "name": name,
                    "roll_number": roll,
                    "confidence": confidence,
                    "image_index": current_image,
                    "timestamp": current_image  # Can be used for ordering
                }
                await publish_to_channel(f"student_recognized:{attendance_id}", student_recognition)
                logger.debug("[face_worker] Published individual student recognition: %s", name)
            else:
                # Duplicate recognition
                label = f"{name} - Duplicate ({confidence}%)"
                color = (255, 255, 0)  # Yellow for duplicate
                logger.debug("[face_worker] Duplicate recognition: %s (ID %s) in image %d", 
                           name, student_id, current_image)
                
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
            logger.debug("[face_worker] Unknown face %d in image %d (confidence=%.1f%%)", 
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
    
    return image_results, img, new_recognitions

async def face_worker():
    logger.info("[face_worker] Starting face recognition worker")
    logger.info("[face_worker] Initializing DB connection...")
    await init_db()
    logger.info("[face_worker] Database connected successfully")

    logger.debug("[face_worker] Connecting to RabbitMQ: %s", settings.rabbitmq_url)
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    logger.info("[face_worker] RabbitMQ connection and channel established")

    queue = await channel.declare_queue(
        "face_recog_queue",
        durable=True,
        arguments={"x-max-priority": 10}
    )
    logger.info("[face_worker] Listening on queue: face_recog_queue")

    async with queue.iterator() as messages:
        async for message in messages:
            async with message.process():
                logger.debug("[face_worker] Received message from queue")
                student_data = None  # Initialize for cleanup
                recognized_set_key = None
                all_annotated_images = []  # Initialize early to avoid undefined errors
                
                try:
                    payload = json.loads(message.body)
                    data = payload.get("data", {})
                    logger.debug("[face_worker] Parsed payload data keys: %s", list(data.keys()))

                    # Extract job parameters
                    attendance_id = data.get("attendance_id")
                    image_base64_list = data.get("image_base64_list", [])
                    num_images = len(image_base64_list)
                    semester = data.get("semester")
                    department = data.get("department")
                    program = data.get("program")
                    academic_year = data.get("academic_year")

                    logger.info("[face_worker] Processing job - attendance_id: %s, images: %d, filters: semester=%s, dept=%s, program=%s, year=%s", 
                               attendance_id, num_images, semester, department, program, academic_year)

                    # Validate required data
                    if not all([attendance_id, image_base64_list, semester, department, program]):
                        logger.error("[face_worker] Missing required data for attendance_id: %s", attendance_id)
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": "Missing required data: attendance_id, images, semester, department, or program"
                        })
                        continue

                    # Convert semester to int
                    try:
                        semester = int(semester)
                        logger.debug("[face_worker] Converted semester to int: %d", semester)
                    except (ValueError, TypeError) as e:
                        logger.error("[face_worker] Invalid semester format: %s, error: %s", semester, str(e))
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": f"Invalid semester format: {semester}"
                        })
                        continue

                    # Initialize Redis set for unique students
                    recognized_set_key = f"recognized_students:{attendance_id}"
                    await redis_client.delete(recognized_set_key)
                    logger.info("[face_worker] Initialized Redis set: %s", recognized_set_key)

                    # Load student data once for the entire job
                    student_data = await load_student_data(semester, department, program, academic_year, attendance_id)
                    if not student_data:
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": f"No students with valid face embeddings found for the given criteria"
                        })
                        continue

                    logger.info("[face_worker] Loaded %d students for recognition", len(student_data['ids']))

                    # Process each image
                    all_results = []
                    total_faces = 0
                    total_new_recognitions = 0

                    for current_image, image_base64 in enumerate(image_base64_list, 1):
                        logger.info("[face_worker] Processing image %d/%d", current_image, num_images)

                        try:
                            # Decode image
                            image_bytes = base64.b64decode(image_base64)
                            nparr = np.frombuffer(image_bytes, np.uint8)
                            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            
                            if img is None:
                                logger.warning("[face_worker] Failed to decode image %d", current_image)
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
                                    "recognized_count": len(await redis_client.smembers(recognized_set_key))
                                })
                                continue

                            # Process the image
                            image_results, annotated_img, new_recognitions = await process_single_image(
                                img, current_image, student_data, recognized_set_key, attendance_id
                            )

                            # Always encode and store the annotated image (even if no faces detected)
                            _, buffer = cv2.imencode('.jpg', annotated_img)
                            annotated_image_base64 = base64.b64encode(buffer).decode('utf-8')
                            
                            # Store annotated image info
                            annotated_image_info = {
                                "image_index": current_image,
                                "status": "processed",
                                "faces_detected": len(image_results),
                                "new_recognitions": new_recognitions,
                                "annotated_image_base64": annotated_image_base64,
                                "message": f"Processed {len(image_results)} faces, {new_recognitions} new recognitions"
                            }
                            all_annotated_images.append(annotated_image_info)

                            if not image_results:
                                # No faces detected but still store the annotated image
                                recognized_count = len(await redis_client.smembers(recognized_set_key))
                                await publish_to_channel(f"face_progress:{attendance_id}", {
                                    "status": "progress",
                                    "current_image": current_image,
                                    "total_images": num_images,
                                    "recognized_count": recognized_count,
                                    "annotated_image_base64": annotated_image_base64,
                                    "message": f"No faces detected in image {current_image}"
                                })
                            else:
                                # Update counters
                                total_faces += len(image_results)
                                total_new_recognitions += new_recognitions

                                # Get current recognition count
                                recognized_count = len(await redis_client.smembers(recognized_set_key))

                                # Publish progress
                                await publish_to_channel(f"face_progress:{attendance_id}", {
                                    "status": "image_processed",
                                    "current_image": current_image,
                                    "total_images": num_images,
                                    "faces_in_image": len(image_results),
                                    "new_recognitions_in_image": new_recognitions,
                                    "total_recognized_count": recognized_count,
                                    "annotated_image_base64": annotated_image_base64,
                                    "message": f"Processed image {current_image}: {len(image_results)} faces, {new_recognitions} new recognitions"
                                })

                                logger.info("[face_worker] Image %d processed: %d faces, %d new recognitions, total unique: %d", 
                                           current_image, len(image_results), new_recognitions, recognized_count)

                                all_results.extend(image_results)

                        except Exception as e:
                            logger.error("[face_worker] Error processing image %d: %s", current_image, str(e))
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
                    if len(all_annotated_images) == 0:
                        logger.error("[face_worker] No images processed successfully for attendance_id: %s", attendance_id)
                        await publish_to_channel(f"face_progress:{attendance_id}", {
                            "status": "failed",
                            "reason": "No images could be processed successfully"
                        })
                    else:
                        # Get final unique students
                        recognized_members = await redis_client.smembers(recognized_set_key)
                        unique_student_ids = [member.decode('utf-8') if isinstance(member, bytes) else str(member) 
                                            for member in recognized_members]
                        
                        logger.info("[face_worker] Building final results for %d unique students", len(unique_student_ids))
                        
                        unique_students = []
                        
                        # Build a lookup dictionary from the already loaded student data
                        if student_data:  # Check if student_data exists
                            student_lookup = {str(doc.student_id): doc for doc in student_data['docs']}
                            
                            for student_id in unique_student_ids:
                                try:
                                    # Use the lookup dictionary instead of database query
                                    student = student_lookup.get(student_id)
                                    if student:
                                        unique_students.append({
                                            "student_id": str(student.student_id),
                                            "name": f"{student.first_name} {student.last_name}".strip(),
                                            "roll_number": student.roll_number,
                                            "email": getattr(student, 'email', 'N/A')
                                        })
                                        logger.debug("[face_worker] Added student to final results: %s", student.first_name + " " + student.last_name)
                                    else:
                                        logger.warning("[face_worker] Student not found in lookup for ID: %s", student_id)
                                except Exception as e:
                                    logger.error("[face_worker] Error processing student %s: %s", student_id, str(e))

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
                        logger.info("[face_worker] Job completed - attendance_id: %s, unique students: %d, total faces: %d", 
                                   attendance_id, len(unique_students), total_faces if 'total_faces' in locals() else 0)

                except Exception as e:
                    logger.error("[face_worker] Unexpected error for attendance_id %s: %s", 
                               attendance_id if 'attendance_id' in locals() else 'unknown', str(e))
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
                            logger.debug("[face_worker] Cleaned up Redis set: %s", recognized_set_key)
                        except Exception as e:
                            logger.error("[face_worker] Error cleaning up Redis set: %s", str(e))

if __name__ == "__main__":
    asyncio.run(face_worker())