from fastapi import HTTPException
from pydantic import ValidationError
from bson import ObjectId

from app.core.database import get_db
async def exception_session(body: dict, user_data: dict):
    if user_data.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can access this route")

    try:
        action = body.get("action",'')
        timetable_id = body.get("timetable_id",'')
        if action == "Cancel":
            print("Current Cancel payload:", body)
            return await handle_cancel_action(body)

        elif action == "Rescheduled":
            print("Current Rescheduled payload:", body)
            return await handle_reschedule_action(body)

        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail",
                    "message": "Unsupported action. Only 'Cancel' and 'Rescheduled' are supported."
                }
            )

    except ValidationError as ve:
        raise HTTPException(status_code=422, detail=ve.errors())


# 🔹 Cancel Handler
async def handle_cancel_action(body: dict):
    timetable_id = body.get("timetable_id")
    slot_ref = body.get("slotReference", {})
    day = slot_ref.get("day")
    index = slot_ref.get("slotIndex")
    
    
    if not ObjectId.is_valid(timetable_id):
        raise HTTPException(status_code=400, detail="Invalid timetable_id format")
    
    
    timetable_collection = get_db().timetables
    timetable = await timetable_collection.find_one({"_id": ObjectId(timetable_id)})
    
    
    if not timetable:
        raise HTTPException(status_code=404, detail="Timetable not found")
    
    schedule = timetable.get("schedule", {})
    
    if day not in schedule:
        raise HTTPException(status_code=400, detail=f"Day '{day}' not found in schedule")

    if not (0 <= index < len(schedule[day])):
        raise HTTPException(status_code=400, detail=f"Invalid slot index '{index}' for day '{day}'")

    # Log the slot to be deleted
    deleted_slot = schedule[day][index]
    print(f"Deleting slot on {day} at index {index}: {deleted_slot}")

    # Remove the slot from the list
    schedule[day].pop(index)

    # Update the document in MongoDB
    result = await timetable_collection.update_one(
        {"_id": ObjectId(timetable_id)},
        {"$set": {f"schedule.{day}": schedule[day]}}
    )


    return {"status": "success", "message": f"Slot on {day} {deleted_slot} cancelled"}

# 🔹 Reschedule Handler
async def handle_reschedule_action(body: dict):
    timetable_id = body.get("timetable_id")
    
    if not ObjectId.is_valid(timetable_id):
        raise HTTPException(status_code=400, detail="Invalid timetable_id format")

    timetable_collection = get_db().timetables
    timetable = await timetable_collection.find_one({"_id": ObjectId(timetable_id)})
    if not timetable:
        raise HTTPException(status_code=404, detail="Timetable not found")

    slot_ref = body.get("slotReference", {})
    new_slot = body.get("newSlot", {})

    day = slot_ref.get("day")
    index = slot_ref.get("slotIndex")
    print("Reschedule Action - Timetable found:", timetable)
    if day not in timetable.get("schedule", {}):
        raise HTTPException(status_code=400, detail=f"Day '{day}' not found in schedule")

    slots = timetable["schedule"][day]
    if not (0 <= index < len(slots)):
        raise HTTPException(status_code=400, detail=f"Invalid slot index '{index}' for day '{day}'")

    # Validate new slot payload
    required_keys = {"startTime", "endTime", "subject"}
    if not required_keys.issubset(new_slot.keys()):
        raise HTTPException(status_code=400, detail=f"Missing keys in newSlot. Required: {required_keys}")

    # Update the slot
    slots[index]["start_time"] = new_slot["startTime"]
    slots[index]["end_time"] = new_slot["endTime"]
    slots[index]["subject"] = new_slot["subject"]  

    # Save to DB
    result = await timetable_collection.update_one(
        {"_id": ObjectId(timetable_id)},
        {"$set": {f"schedule.{day}": slots}}
    )


    return {"status": "success", "message": f"Slot on {day} Subject: {new_slot["subject"] } reschedule to {new_slot["startTime"]} : {new_slot["endTime"]} "}