import math

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from database import events
from models.event import EventCreate, EventUpdate, EventOut
from utils.auth import get_current_user

router = APIRouter(prefix="/events", tags=["events"])


def _to_event_out(doc: dict) -> EventOut:
    return EventOut(
        id=str(doc["_id"]),
        owner_id=str(doc.get("owner_id", "")),
        title=doc["title"],
        subject=doc.get("subject", ""),
        date=doc["date"],
        time=doc["time"],
        reminder_before=doc.get("reminder_before", 15),
        location=doc.get("location", ""),
        notes=doc.get("notes", ""),
        completed=doc.get("completed", False),
        attended=doc.get("attended"),
        duration_minutes=doc.get("duration_minutes"),
    )


@router.get("/", response_model=list[EventOut])
def list_events(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    cursor = events.find({"owner_id": user_id}).sort("date", 1).sort("time", 1)
    return [_to_event_out(doc) for doc in cursor]


@router.post("/", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(body: EventCreate, current_user: dict = Depends(get_current_user)):
    doc = body.dict()
    doc["owner_id"] = str(current_user["_id"])
    result = events.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _to_event_out(doc)


@router.put("/{id}", response_model=EventOut)
def update_event(id: str, body: EventUpdate, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid event id")
    doc = events.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Event not found")
    update_data = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    events.update_one({"_id": oid}, {"$set": update_data})
    updated = events.find_one({"_id": oid})
    return _to_event_out(updated)


@router.delete("/{id}", response_model=dict)
def delete_event(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid event id")
    doc = events.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Event not found")
    events.delete_one({"_id": oid})
    return {"ok": True}


class AttendanceBody(BaseModel):
    attended: bool


@router.put("/{id}/attendance", response_model=EventOut)
def mark_attendance(id: str, body: AttendanceBody, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid event id")
    doc = events.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Event not found")
    events.update_one({"_id": oid}, {"$set": {"attended": body.attended}})
    updated = events.find_one({"_id": oid})
    return _to_event_out(updated)


class SubjectSummary(BaseModel):
    title: str
    total: int
    attended: int
    missed: int
    unmarked: int
    percentage: float
    can_skip: int


@router.get("/attendance/summary", response_model=list[SubjectSummary])
def attendance_summary(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    all_events = list(events.find({"owner_id": user_id}))

    groups: dict[str, list] = {}
    for e in all_events:
        key = (e.get("title") or "").strip().lower()
        if not key:
            continue
        groups.setdefault(key, []).append(e)

    result = []
    for key, evts in sorted(groups.items()):
        display_title = evts[0]["title"]
        total = len(evts)
        attended_count = sum(1 for e in evts if e.get("attended") is True)
        missed_count = sum(1 for e in evts if e.get("attended") is False)
        unmarked_count = sum(1 for e in evts if e.get("attended") is None)
        marked = attended_count + missed_count
        pct = (attended_count / marked * 100) if marked > 0 else 0.0
        can_skip = math.floor(attended_count * 4 / 3) - marked if marked > 0 else 0
        if can_skip < 0:
            can_skip = 0
        result.append(SubjectSummary(
            title=display_title,
            total=total,
            attended=attended_count,
            missed=missed_count,
            unmarked=unmarked_count,
            percentage=round(pct, 1),
            can_skip=can_skip,
        ))

    return result
