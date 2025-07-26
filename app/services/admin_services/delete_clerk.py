
from fastapi import HTTPException
from app.core.redis import redis_client
import json
from app.core.database import get_db
from bson import ObjectId
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from app.utils.publisher import send_to_queue  
from pymongo.errors import PyMongoError

# JSON encoder to handle ObjectId and datetime
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)



async def delete_clerk(email_id, user_data):

    print(f"🧾 user_data = {user_data}")  # 🔍 Inspect structure
    
    user_email = user_data["email"]
    user_role = user_data["role"]
    email_id = email_id.lower()
    print(f"➡️ Requested by: {user_email} (Role: {user_role}, Clerk Email: {email_id})")

    if user_role != "admin":
        print("❌ Access denied: Not an Admin")
        raise HTTPException(
            status_code=403,
            detail={"status": "fail", "message": "Only Admin can access this route"}
        )
        
    # Fetch the clerk by email
    clerk_collection = get_db().clerks
    clerk = await clerk_collection.find_one({"email": email_id})

    if not clerk:
        print(f"❌ Clerk with email '{email_id}' not found")
        raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": f"Clerk with email '{email_id}' not found"}
        )
    
    print(f"✅ Clerk found: {clerk}")
    
    # Step 2: Delete the clerk
    try:
        delete_result = await clerk_collection.delete_one({"email": email_id})
        if delete_result.deleted_count == 0:
            raise Exception("MongoDB delete failed unexpectedly")

        print(f"🗑️ Clerk with email '{email_id}' deleted from database")
    except PyMongoError as e:
        print("❌ MongoDB error:", str(e))
        raise HTTPException(status_code=500, detail={"status": "fail", "message": "Error deleting clerk from database"})

    # 🔍 Clean up any related Redis cache 
    try:
        clerk_department= clerk.get('department','')
        async for key in redis_client.scan_iter("*"):
            key_str = key.decode() if isinstance(key, bytes) else key
            if f"clerk:{clerk_department}" in key_str:
                await redis_client.delete(key)
                print(f"🧹 Deleted Redis key: {key_str}")
    except Exception as e:
        await clerk_collection.insert_one(clerk)
        raise HTTPException(
            status_code=500,
            detail={"status": "fail", "message": f"Error deleting clerk from Redis: {str(e)}"}
        )
        
    # Step 3: Try sending email – rollback if fails
    # try:
    #     await send_to_queue("email_queue", {
    #         "type": "send_email",
    #         "data": {
    #             "to": email_id,
    #             "subject": "Your MarkMe Clerk Account Has Been Deleted",
    #             "body": (
    #                 f"Dear Clerk,\n\n"
    #                 f"Your MarkMe account associated with '{email_id}' has been deleted successfully by the admin.\n"
    #                 f"If you think this was a mistake, please contact support.\n\n"
    #                 f"Regards,\nMarkMe Team"
    #             )
    #         }
    #     }, priority=5)

    #     print("📤 Sent delete email notification task to queue")

    # except Exception as e:
    #     print("❌ Failed to send email")

    # ✅ If everything succeeds
    return {
        "status": "success",
        "message": f"Clerk with email '{email_id}' deleted successfully"
    }