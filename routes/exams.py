from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from database import exams
from models.exam import ExamCreate, ExamUpdate, ExamOut
from utils.auth import get_current_user

router = APIRouter(prefix="/exams", tags=["exams"])


def _to_out(doc: dict) -> ExamOut:
    return ExamOut(
        id=str(doc["_id"]),
        owner_id=str(doc.get("owner_id", "")),
        title=doc["title"],
        subject=doc.get("subject", ""),
        exam_type=doc.get("exam_type", "internal"),
        date=doc.get("date", ""),
        time=doc.get("time", "09:00"),
        duration_minutes=doc.get("duration_minutes", 120),
        location=doc.get("location", ""),
        notes=doc.get("notes", ""),
        reminder_minutes=doc.get("reminder_minutes", 30),
        completed=doc.get("completed", False),
        created_at=doc.get("created_at", ""),
    )


@router.get("/", response_model=list[ExamOut])
def list_exams(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    cursor = exams.find({"owner_id": user_id}).sort("date", 1).sort("time", 1)
    return [_to_out(doc) for doc in cursor]


@router.get("/upcoming", response_model=list[ExamOut])
def list_upcoming(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    today = datetime.now().strftime("%Y-%m-%d")
    cursor = exams.find({
        "owner_id": user_id,
        "completed": False,
        "date": {"$gte": today},
    }).sort("date", 1).sort("time", 1)
    return [_to_out(doc) for doc in cursor]


@router.post("/", response_model=ExamOut, status_code=status.HTTP_201_CREATED)
def create_exam(body: ExamCreate, current_user: dict = Depends(get_current_user)):
    doc = body.dict()
    doc["owner_id"] = str(current_user["_id"])
    doc["completed"] = False
    doc["created_at"] = datetime.now().isoformat()
    result = exams.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _to_out(doc)


@router.put("/{id}", response_model=ExamOut)
def update_exam(id: str, body: ExamUpdate, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid exam id")
    doc = exams.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Exam not found")
    update_data = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    exams.update_one({"_id": oid}, {"$set": update_data})
    updated = exams.find_one({"_id": oid})
    return _to_out(updated)


@router.delete("/{id}", response_model=dict)
def delete_exam(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid exam id")
    doc = exams.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Exam not found")
    exams.delete_one({"_id": oid})
    return {"ok": True}


@router.put("/{id}/toggle", response_model=ExamOut)
def toggle_exam(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid exam id")
    doc = exams.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Exam not found")
    new_status = not doc.get("completed", False)
    exams.update_one({"_id": oid}, {"$set": {"completed": new_status}})
    updated = exams.find_one({"_id": oid})
    return _to_out(updated)
