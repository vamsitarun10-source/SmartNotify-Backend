from datetime import datetime, timedelta
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from database import timetable, events
from models.timetable import TimetableEntryCreate, TimetableEntryUpdate, TimetableEntryOut
from models.event import EventCreate, EventOut
from utils.auth import get_current_user

router = APIRouter(prefix="/timetable", tags=["timetable"])

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _to_entry_out(doc: dict) -> TimetableEntryOut:
    return TimetableEntryOut(
        id=str(doc["_id"]),
        owner_id=str(doc.get("owner_id", "")),
        title=doc["title"],
        subject=doc.get("subject", ""),
        day_of_week=doc["day_of_week"],
        time=doc["time"],
        duration_minutes=doc.get("duration_minutes", 60),
        reminder_before=doc.get("reminder_before", 15),
        location=doc.get("location", ""),
        notes=doc.get("notes", ""),
    )


@router.get("/", response_model=list[TimetableEntryOut])
def list_entries(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    cursor = timetable.find({"owner_id": user_id}).sort("day_of_week", 1).sort("time", 1)
    return [_to_entry_out(doc) for doc in cursor]


@router.post("/", response_model=TimetableEntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(body: TimetableEntryCreate, current_user: dict = Depends(get_current_user)):
    doc = body.dict()
    doc["owner_id"] = str(current_user["_id"])
    result = timetable.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _to_entry_out(doc)


@router.put("/{id}", response_model=TimetableEntryOut)
def update_entry(id: str, body: TimetableEntryUpdate, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid entry id")
    doc = timetable.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Entry not found")
    update_data = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    timetable.update_one({"_id": oid}, {"$set": update_data})
    updated = timetable.find_one({"_id": oid})
    return _to_entry_out(updated)


@router.delete("/{id}", response_model=dict)
def delete_entry(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid entry id")
    doc = timetable.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Entry not found")
    timetable.delete_one({"_id": oid})
    return {"ok": True}


@router.post("/generate", response_model=dict)
def generate_events(
    weeks: int = 4,
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["_id"])
    entries = list(timetable.find({"owner_id": user_id}))
    if not entries:
        return {"created": 0, "message": "No timetable entries found."}

    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    created_count = 0
    start_date = monday
    end_date = monday + timedelta(weeks=weeks)

    existing_dates = set()
    for ev in events.find({"owner_id": user_id}, {"date": 1, "title": 1, "time": 1}):
        existing_dates.add((ev["date"], ev["title"], ev["time"]))

    for entry in entries:
        current = monday
        while current < end_date:
            if current.weekday() == entry["day_of_week"]:
                date_str = current.strftime("%Y-%m-%d")
                key = (date_str, entry["title"], entry["time"])
                if key not in existing_dates:
                    event_doc = {
                        "owner_id": user_id,
                        "title": entry["title"],
                        "subject": entry.get("subject", ""),
                        "date": date_str,
                        "time": entry["time"],
                        "reminder_before": entry.get("reminder_before", 15),
                        "location": entry.get("location", ""),
                        "notes": entry.get("notes", ""),
                        "completed": False,
                    }
                    events.insert_one(event_doc)
                    existing_dates.add(key)
                    created_count += 1
            current += timedelta(days=1)

    return {
        "created": created_count,
        "message": f"Generated {created_count} events for {weeks} weeks.",
    }
