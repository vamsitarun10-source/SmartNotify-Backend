from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from database import tasks
from models.task import TaskCreate, TaskUpdate, TaskOut
from utils.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _to_task_out(doc: dict) -> TaskOut:
    return TaskOut(
        id=str(doc["_id"]),
        owner_id=str(doc.get("owner_id", "")),
        title=doc["title"],
        priority=doc.get("priority", "medium"),
        due_date=doc.get("due_date", ""),
        due_time=doc.get("due_time", ""),
        reminder_minutes=doc.get("reminder_minutes", 0),
        category=doc.get("category", "general"),
        notes=doc.get("notes", ""),
        completed=doc.get("completed", False),
        created_at=doc.get("created_at", ""),
    )


@router.get("/", response_model=list[TaskOut])
def list_tasks(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    cursor = tasks.find({"owner_id": user_id}).sort("due_date", 1).sort("due_time", 1)
    return [_to_task_out(doc) for doc in cursor]


@router.get("/today", response_model=list[TaskOut])
def list_today_tasks(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    today = datetime.now().strftime("%Y-%m-%d")
    cursor = tasks.find({"owner_id": user_id, "due_date": today, "completed": False}).sort("due_time", 1)
    return [_to_task_out(doc) for doc in cursor]


@router.post("/", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreate, current_user: dict = Depends(get_current_user)):
    doc = body.dict()
    doc["owner_id"] = str(current_user["_id"])
    doc["created_at"] = datetime.now().isoformat()
    result = tasks.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _to_task_out(doc)


@router.put("/{id}", response_model=TaskOut)
def update_task(id: str, body: TaskUpdate, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task id")
    doc = tasks.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Task not found")
    update_data = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    tasks.update_one({"_id": oid}, {"$set": update_data})
    updated = tasks.find_one({"_id": oid})
    return _to_task_out(updated)


@router.delete("/{id}", response_model=dict)
def delete_task(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task id")
    doc = tasks.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Task not found")
    tasks.delete_one({"_id": oid})
    return {"ok": True}


@router.put("/{id}/toggle", response_model=TaskOut)
def toggle_task(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task id")
    doc = tasks.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Task not found")
    new_status = not doc.get("completed", False)
    tasks.update_one({"_id": oid}, {"$set": {"completed": new_status}})
    updated = tasks.find_one({"_id": oid})
    return _to_task_out(updated)
