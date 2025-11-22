from fastapi import APIRouter
import aio_pika
import json
from app.core.rabbitmq_config import settings
from app.models.allModel import NotificationRequest
from app.services.common_services.notify_users import notify_users

router = APIRouter()

@router.post("/notify")
async def notify(request : NotificationRequest):
    print("came here")
    return await notify_users(request)
