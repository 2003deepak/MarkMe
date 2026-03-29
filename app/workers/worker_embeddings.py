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

# faiss cache
from app.core.faiss_cache import faiss_cache, get_cache_key

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# suppress logs
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['INSIGHTFACE_LOG_LEVEL'] = 'ERROR'
warnings.filterwarnings("ignore")


async def connect_rabbitmq():
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            logger.info("✅ Connected to RabbitMQ")
            return connection
        except Exception as e:
            logger.warning(f"RabbitMQ not ready, retrying... {e}")
            await asyncio.sleep(5)


async def generate_embedding(student_id: str, image_paths: List[str]):

    try:
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

        # invalidate FAISS cache
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
        raise  # important for retry

    finally:
        # cleanup temp files
        for path in image_paths:
            try:
                os.remove(path)
            except Exception:
                pass


async def process_message(message: aio_pika.IncomingMessage):

    try:
        payload = json.loads(message.body.decode())
        data = payload.get("data", {})

        student_id = data.get("student_id")
        image_paths = data.get("image_paths")

        if not student_id or not image_paths:
            logger.warning("⚠️ Missing student_id or image_paths")
            await message.ack()
            return

        await generate_embedding(student_id, image_paths)

        # success → ACK
        await message.ack()

    except Exception as e:
        logger.error(f"❌ Error processing message: {str(e)}", exc_info=True)

        # reject → requeue
        await message.nack(requeue=True)


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


if __name__ == "__main__":
    try:
        asyncio.run(embedding_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped")