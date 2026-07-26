from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from database import calendar_events
from models.calendar_event import CalendarEventCreate, CalendarEventUpdate, CalendarEventOut
from utils.auth import get_current_user

router = APIRouter(prefix="/calendar", tags=["calendar"])


def _to_out(doc: dict) -> CalendarEventOut:
    return CalendarEventOut(
        id=str(doc["_id"]),
        owner_id=str(doc.get("owner_id", "")),
        title=doc["title"],
        date=doc["date"],
        category=doc.get("category", "personal"),
        notes=doc.get("notes", ""),
        created_at=doc.get("created_at", ""),
    )


@router.get("/", response_model=list[CalendarEventOut])
def list_events(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    cursor = calendar_events.find({"owner_id": user_id}).sort("date", 1)
    return [_to_out(doc) for doc in cursor]


@router.post("/", response_model=CalendarEventOut, status_code=status.HTTP_201_CREATED)
def create_event(body: CalendarEventCreate, current_user: dict = Depends(get_current_user)):
    doc = body.dict()
    doc["owner_id"] = str(current_user["_id"])
    doc["created_at"] = datetime.now().isoformat()
    result = calendar_events.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _to_out(doc)


@router.put("/{id}", response_model=CalendarEventOut)
def update_event(id: str, body: CalendarEventUpdate, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    doc = calendar_events.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Not found")
    update_data = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    calendar_events.update_one({"_id": oid}, {"$set": update_data})
    updated = calendar_events.find_one({"_id": oid})
    return _to_out(updated)


@router.delete("/{id}", response_model=dict)
def delete_event(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    doc = calendar_events.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Not found")
    calendar_events.delete_one({"_id": oid})
    return {"ok": True}
