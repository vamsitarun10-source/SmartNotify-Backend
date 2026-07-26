from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status, Query

from database import notes
from models.note import NoteCreate, NoteUpdate, NoteOut
from utils.auth import get_current_user

router = APIRouter(prefix="/notes", tags=["notes"])


def _to_out(doc: dict) -> NoteOut:
    return NoteOut(
        id=str(doc["_id"]),
        owner_id=str(doc.get("owner_id", "")),
        title=doc["title"],
        content=doc.get("content", ""),
        subject=doc.get("subject", ""),
        note_type=doc.get("note_type", "text"),
        attachments=doc.get("attachments", []),
        pinned=doc.get("pinned", False),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


@router.get("/subjects", response_model=list[str])
def get_subjects(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    pipeline = [
        {"$match": {"owner_id": user_id, "subject": {"$ne": ""}}},
        {"$group": {"_id": "$subject"}},
        {"$sort": {"_id": 1}},
    ]
    results = notes.aggregate(pipeline)
    return [r["_id"] for r in results]


@router.get("/", response_model=list[NoteOut])
def list_notes(
    q: str = Query(None, description="Search query"),
    subject: str = Query(None, description="Filter by subject"),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["_id"])
    query = {"owner_id": user_id}

    if subject:
        query["subject"] = subject

    cursor = notes.find(query).sort([("pinned", -1), ("updated_at", -1)])
    results = [_to_out(doc) for doc in cursor]

    if q:
        q_lower = q.lower()
        results = [
            n for n in results
            if q_lower in n.title.lower() or q_lower in n.content.lower()
        ]

    return results


@router.post("/", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def create_note(body: NoteCreate, current_user: dict = Depends(get_current_user)):
    doc = body.dict()
    doc["owner_id"] = str(current_user["_id"])
    now = datetime.now().isoformat()
    doc["created_at"] = now
    doc["updated_at"] = now
    result = notes.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _to_out(doc)


@router.put("/{id}", response_model=NoteOut)
def update_note(id: str, body: NoteUpdate, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid note id")
    doc = notes.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Note not found")
    update_data = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()
    notes.update_one({"_id": oid}, {"$set": update_data})
    updated = notes.find_one({"_id": oid})
    return _to_out(updated)


@router.delete("/{id}", response_model=dict)
def delete_note(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid note id")
    doc = notes.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Note not found")
    notes.delete_one({"_id": oid})
    return {"ok": True}


@router.put("/{id}/pin", response_model=NoteOut)
def toggle_pin(id: str, current_user: dict = Depends(get_current_user)):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid note id")
    doc = notes.find_one({"_id": oid})
    if not doc or doc.get("owner_id") != str(current_user["_id"]):
        raise HTTPException(status_code=404, detail="Note not found")
    new_pinned = not doc.get("pinned", False)
    notes.update_one({"_id": oid}, {"$set": {"pinned": new_pinned, "updated_at": datetime.now().isoformat()}})
    updated = notes.find_one({"_id": oid})
    return _to_out(updated)
