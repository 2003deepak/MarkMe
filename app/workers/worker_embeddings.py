import asyncio
import aio_pika
import json
import os
import warnings
import logging
from typing import List
from bson import ObjectId

from app.core.rabbitmq_config import settings
from app.utils.extract_student_embedding import extract_student_embedding
from app.core.database import init_db
from app.schemas.student import Student
from app.core.faiss_cache import faiss_cache, get_cache_key

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# suppress logs
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['INSIGHTFACE_LOG_LEVEL'] = 'ERROR'
warnings.filterwarnings("ignore")

MAX_RETRIES = 3


# ---------------- RABBITMQ CONNECTION ----------------
async def connect_rabbitmq():
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            logger.info("✅ Connected to RabbitMQ")
            return connection
        except Exception as e:
            logger.warning(f"RabbitMQ not ready, retrying... {e}")
            await asyncio.sleep(5)


# ---------------- EMBEDDING LOGIC ----------------
async def generate_embedding(student_id: str, image_paths: List[str]):

    # normalize paths
    image_paths = [os.path.abspath(p) for p in image_paths]

    try:
        # validate paths
        for path in image_paths:
            if not os.path.exists(path):
                raise ValueError(f"Invalid image path: {path}")

        face_embedding = await extract_student_embedding(image_paths)

        # validate embedding
        if face_embedding is None or len(face_embedding) != 512:
            raise ValueError("Invalid embedding generated")

        student = await Student.find_one(Student.id == ObjectId(student_id))

        if not student:
            logger.error(f"Student not found: {student_id}")
            return

        # update embedding
        await student.update({
            "$set": {
                "face_embedding": face_embedding.tolist()
            }
        })

        logger.info(f"✅ Embedding stored for student: {student_id}")

        # invalidate cache
        if student.semester and student.department and student.program:
            cache_key = get_cache_key(
                student.semester,
                student.department,
                student.program
            )
            faiss_cache.pop(cache_key, None)
            logger.info(f"🧹 Cache invalidated: {cache_key}")

    except Exception as e:
        logger.error(f"❌ Embedding generation failed for {student_id}: {str(e)}", exc_info=True)
        raise

    finally:
        # cleanup temp files
        for path in image_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"Cleanup failed: {e}")


# ---------------- MESSAGE PROCESSOR ----------------
async def process_message(message: aio_pika.IncomingMessage):
    try:
        payload = json.loads(message.body.decode())
        data = payload.get("data", {})
        retry = payload.get("retry", 0)

        student_id = data.get("student_id")
        image_paths = data.get("image_paths")

        if not student_id or not image_paths:
            logger.warning("⚠️ Missing student_id or image_paths")
            await message.ack()
            return

        await generate_embedding(student_id, image_paths)

        # success
        await message.ack()

    except Exception as e:
        logger.error(f"❌ Error processing message: {str(e)}", exc_info=True)

        payload = json.loads(message.body.decode())
        retry = payload.get("retry", 0)

        if retry < MAX_RETRIES:
            payload["retry"] = retry + 1

            logger.warning(f"🔁 Retrying ({retry+1}/{MAX_RETRIES})")
            
            channel = await message.channel.get_channel()

            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(payload).encode(),
                    priority=message.priority
                ),
                routing_key=message.routing_key,
            )
        else:
            logger.error(f"💀 Max retries exceeded: {payload}")

        # always ACK original message (IMPORTANT)
        await message.ack()


# ---------------- WORKER ----------------
async def embedding_worker():

    await init_db()
    logger.info("✅ Database connected")

    connection = await connect_rabbitmq()

    async with connection:
        channel = await connection.channel()

        await channel.set_qos(prefetch_count=1)

        queue = await channel.declare_queue(
            settings.embedding_queue,
            durable=True,
            arguments={"x-max-priority": 10}
        )

        logger.info(f"👂 Listening on queue: {settings.embedding_queue}")

        async with queue.iterator() as messages:
            async for message in messages:
                await process_message(message)


# ---------------- ENTRY ----------------
if __name__ == "__main__":
    try:
        asyncio.run(embedding_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped")