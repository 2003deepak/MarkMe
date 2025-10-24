from fastapi import APIRouter
from fastapi import Body


router = APIRouter()

# General-purpose routes
@router.get("/health")
async def health_check():
    return {"success" : True , "status": "healthy"}