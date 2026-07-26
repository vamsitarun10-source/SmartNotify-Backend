import io
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import events, timetable, tasks, assignments, exams, calendar_events, notes
from utils.auth import get_current_user

router = APIRouter(prefix="/backup", tags=["backup"])

CURRENT_VERSION = 1

COLLECTIONS = {
    "events": events,
    "timetable": timetable,
    "tasks": tasks,
    "assignments": assignments,
    "exams": exams,
    "calendar_events": calendar_events,
    "notes": notes,
}

FIELDS_TO_STRIP = {"_id", "owner_id", "__v"}


def _clean_doc(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in FIELDS_TO_STRIP}


@router.get("/export")
def export_backup(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    data = {}
    for name, collection in COLLECTIONS.items():
        cursor = collection.find({"owner_id": user_id})
        data[name] = [_clean_doc(doc) for doc in cursor]

    backup = {
        "version": CURRENT_VERSION,
        "app": "ClassReminder",
        "exported_at": datetime.now().isoformat(),
        "user": {
            "name": current_user.get("name", ""),
            "email": current_user.get("email", ""),
        },
        "data": data,
    }

    content = json.dumps(backup, indent=2, default=str)
    filename = f"classreminder_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class ImportBody(BaseModel):
    backup: dict
    replace: bool = False


@router.post("/import")
def import_backup(body: ImportBody, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    backup = body.backup

    version = backup.get("version", 0)
    if version > CURRENT_VERSION:
        raise HTTPException(status_code=400, detail=f"Incompatible backup version {version}. Current version is {CURRENT_VERSION}.")
    if backup.get("app") != "ClassReminder":
        raise HTTPException(status_code=400, detail="Invalid backup file. Must be a ClassReminder backup.")

    data = backup.get("data", {})
    total_imported = 0

    for name, collection in COLLECTIONS.items():
        items = data.get(name, [])
        if not items:
            continue

        if body.replace:
            collection.delete_many({"owner_id": user_id})

        for item in items:
            if body.replace:
                item["owner_id"] = user_id
                collection.insert_one(item)
                total_imported += 1
            else:
                dedup_key = item.get("title", "") + "|" + item.get("date", "") + "|" + item.get("time", "")
                if dedup_key and dedup_key != "|":
                    query = {"owner_id": user_id, "title": item.get("title", "")}
                    if item.get("date"):
                        query["date"] = item["date"]
                    if collection.find_one(query):
                        continue
                item["owner_id"] = user_id
                collection.insert_one(item)
                total_imported += 1

    return {"imported": total_imported, "message": f"Imported {total_imported} items."}
