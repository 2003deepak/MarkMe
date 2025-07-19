from fastapi import APIRouter, Depends, Body,Path
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.admin_services.create_clerk import create_clerk
from app.services.admin_services.get_clerk import get_clerk,get_clerk_by_id
from app.middleware.is_logged_in import is_logged_in
from app.models.allModel import CreateClerkRequest

router = APIRouter()
security = HTTPBearer()  # Define security scheme

@router.post("/clerk/create")
async def create_clerk_route(
    request: CreateClerkRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    
    return await create_clerk(request,user_data)



# In this route, fetch all clerks listed under the given department
# Step 1: Check the role of the user (from the token). Proceed only if the user is a "admin"
# Step 2: This will be a GET request and does not require a request body
# Step 4: Check if the clerk for this department are already stored in Redis Cache
#         - If cached data exists, return it directly
#         - If not, fetch the clerk list from MongoDB where department matches
#           - While fetching from MongoDB, exclude the fields: created_at and updated_at
#           - Store the clerk list efficiently in Redis cache for future use
# Step 5: Return the clerk list as the response

# Note ( Pls refer to the code in app/services/teacher_services/get_all_teachers.py for implementation details):
# ( This functions is having similar implementation as get_all_teachers function in app/services/teacher_services/get_all_teachers.py)

@router.get("/clerk/{deptartment}")
async def get_subject(
    department: str = Path(..., description="Departement to fetch clerks for"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_clerk(department,user_data)




# In this route, fetch detailed data for a specific clerk by their ID

# Step 1: Verify the user's role using the token — only allow access if the user is a "admin"

# Step 2: This is a GET request — the clerk_id will be passed as a path parameter (not in the body)

# Step 3: Check if clerk data (for that department) is available in Redis Cache
#         - If present, return the specific subject data using the subject_id
#         - If not present in cache:
#           - Fetch the clerk list from MongoDB where department matches
#           - Exclude unnecessary fields: created_at, updated_at
#           - Store the list of subjects efficiently in Redis Cache
#           - Return the requested subject's details from the fetched data

# Step 5: Return the clerk data as the response



@router.get("/clerk/{clerk_id}")
async def get_subject_by_id_route(
    clerk_id: str = Path(..., description="Clerk ID to fetch details for"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_clerk_by_id(clerk_id, user_data)


    