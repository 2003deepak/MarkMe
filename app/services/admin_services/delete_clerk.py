from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from app.core.redis import redis_client
import json
from app.schemas.clerk import Clerk  
from bson import ObjectId
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from app.utils.publisher import send_to_queue
from beanie import PydanticObjectId
from beanie.odm.operators.find.comparison import In

# JSON encoder to handle ObjectId and datetime
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

async def delete_clerk(request : Request , email_id: str):
  
    user_email = request.state.user.get("email")
    user_role = request.state.user.get("role")
    email_id = email_id.lower()
    print(f"➡️ Requested by: {user_email} (Role: {user_role}, Clerk Email: {email_id})")

    if user_role != "admin":
        print("❌ Access denied: Not an Admin")
        
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "Only Admin can access this route"
            }
        )
        
    # Fetch the clerk by email using Beanie
    clerk = await Clerk.find_one(Clerk.email == email_id)

    if not clerk:

        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": f"Clerk with email '{email_id}' not found"
            }
        )
    
    # Step 2: Delete the clerk
    try:
        await clerk.delete()
        print(f"🗑️ Clerk with email '{email_id}' deleted from database")
    except Exception as e:
        print("❌ Database error:", str(e))
        
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Error deleting clerk from database"
            }
        )


    # 🔍 Clean up any related Redis cache 
    cache_keys = [
        f"clerks:{clerk.department}",
        f"clerk:{clerk.email}"
    ]

    await redis_client.delete(*cache_keys) 


        
    # Step 3: Try sending email – rollback if fails
    try:
        await send_to_queue("email_queue", {
            "type": "send_email",
            "data": {
                "to": email_id,
                "subject": "Your MarkMe Clerk Account Has Been Deleted",
                "body": (
                    f"Dear Clerk,\n\n"
                    f"Your MarkMe account associated with '{email_id}' has been deleted successfully by the admin.\n"
                    f"If you think this was a mistake, please contact support.\n\n"
                    f"Regards,\nMarkMe Team"
                )
            }
        }, priority=5)

        print("📤 Sent delete email notification task to queue")

    except Exception as e:
        print("❌ Failed to send email")

    # ✅ If everything succeeds
    
    return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": f"Clerk with email '{email_id}' deleted successfully"
            }
        )
    
    