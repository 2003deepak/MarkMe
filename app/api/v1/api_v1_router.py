from fastapi import APIRouter
from app.api.v1.routes import health

api_v1_router = APIRouter()
api_v1_router.include_router(health.router)

