from fastapi import FastAPI
from app.api.v1.routes.auth_router import router as auth_router
from app.api.v1.routes.student_router import router as student_router
from app.api.v1.routes.clerk_router import router as clerk_router
from app.api.v1.routes.admin_router import router as admin_router

app = FastAPI()

# routers
app.include_router(router, prefix="/api/v1/auth")
app.include_router(router, prefix="/api/v1/student")
app.include_router(router, prefix="/api/v1/clerk")
app.include_router(router, prefix="/api/v1/admin")
