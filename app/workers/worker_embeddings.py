import asyncio
import aio_pika
import json
import os
import warnings
from typing import List
from app.core.rabbitmq_config import settings
from app.utils.extract_student_embedding import extract_student_embedding
from app.core.database import get_db, init_db

# Suppress all unnecessary output
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['INSIGHTFACE_LOG_LEVEL'] = 'ERROR'
warnings.filterwarnings("ignore")

async def generate_embedding(student_id: str, image_paths: List[str]):
    """Generate and store face embedding for a student"""
    try:
        db = get_db()
        face_embedding = await extract_student_embedding(image_paths)
        await db.students.update_one(
            {"student_id": student_id},
            {"$set": {"face_embedding": face_embedding.tolist()}}
        )
        print(f"Processed student: {student_id}")
    finally:
        # Silent cleanup
        for path in image_paths:
            try:
                os.remove(path)
            except:
                pass

async def process_message(message: aio_pika.IncomingMessage):
    """Process a single message from the queue"""
    async with message.process():
        try:
            payload = json.loads(message.body.decode())
            data = payload.get("data", {})
            if (student_id := data.get("student_id")) and (image_paths := data.get("image_paths")):
                await generate_embedding(student_id, image_paths)
        except:
            pass  # Silent error handling

async def embedding_worker():
    """Main worker function"""
    await init_db()
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()

        await channel.set_qos(prefetch_count=1)

        queue = await channel.declare_queue(
            settings.embedding_queue,
            durable=True,
            arguments={"x-max-priority": 10}  
        )
        
        async with queue.iterator() as messages:
            async for message in messages:
                await process_message(message)

if __name__ == "__main__":
    try:
        asyncio.run(embedding_worker())
    except KeyboardInterrupt:
        pass