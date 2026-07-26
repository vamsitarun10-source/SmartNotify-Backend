from datetime import datetime, timedelta
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from database import assignments
from models.assignment import AssignmentCreate, AssignmentUpdate, AssignmentOut
from utils.auth import get_current_user

router = APIRouter(prefix="/assignments", tags=["assignments"])


def _to_out(doc: dict) -> AssignmentOut:
    return AssignmentOut(
        id=str(doc["_id"]),
        owner_id=str(doc.get("owner_id", "")),
        title=doc["title"],
        subject=doc.get("subject", ""),
        due_date=doc.get("due_date", ""),
        due_time=doc.get("due_time", "23:59"),
        priority=doc.get("priority", "medium"),
        notes=doc.get("notes", ""),
        attachment=doc.get("attachment", ""),
        reminder_minutes=doc.get("reminder_minutes", 0),
        completed=doc.get("completed", False),
        created_at=doc.get("created_at", ""),
    )


@router.get("/", response_model=list[AssignmentOut])
def list_assignments(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    cursor = assignments.find({"owner_id": user_id}).sort("due_date", 1).sort("due_time", 1)
    return [_to_out(doc) for doc in cursor]


@router.get("/today", response_model=list[AssignmentOut])
def list_today(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    today = datetime.now().strftime("%Y-%m-%d")
    cursor = assignments.find({"owner_id": user_id, "due_date": today, "completed": False}).sort("due_time", 1)
    return [_to_out(doc) for doc in cursor]


@router.get("/upcoming", response_model=list[AssignmentOut])
def list_upcoming(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    today = datetime.now().strftime("%Y-%m-%d")
    week_later = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    cursor = assignments.find({
        "owner_id": user_id,
        "completed": False,
        "due_date": {"$gte": today, "$lte": week_later},
    }).sort("due_date", 1).sort("due_time", 1)
    return [_to_out(doc) for doc in cursor]


@router.post("/", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(body: AssignmentCreate, current_user: dict = Depends(get_current_user)):
    doc = body.dict()
    doc["owner_id"] = str(current_user["_id"])
    doc["created_at"] = datetime.now().isoformat()
    result = assignments.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _to_out(doc)


@router.put("/{id}", response_model=AssignmentOut)
def update_assignment(id: str, body: AssignmentUpdate, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid assignment id")
    doc = assignments.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Assignment not found")
    update_data = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    assignments.update_one({"_id": oid}, {"$set": update_data})
    updated = assignments.find_one({"_id": oid})
    return _to_out(updated)


@router.delete("/{id}", response_model=dict)
def delete_assignment(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid assignment id")
    doc = assignments.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Assignment not found")
    assignments.delete_one({"_id": oid})
    return {"ok": True}


@router.put("/{id}/toggle", response_model=AssignmentOut)
def toggle_assignment(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid assignment id")
    doc = assignments.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Assignment not found")
    new_status = not doc.get("completed", False)
    assignments.update_one({"_id": oid}, {"$set": {"completed": new_status}})
    updated = assignments.find_one({"_id": oid})
    return _to_out(updated)
