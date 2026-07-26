from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from database import events, tasks, assignments, exams, notes, timetable
from utils.auth import get_current_user

router = APIRouter(prefix="/search", tags=["search"])


class SearchResult(BaseModel):
    category: str
    items: list


@router.get("/", response_model=list[SearchResult])
def global_search(
    q: str = Query(..., min_length=1),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["_id"])
    query = q.lower()
    results = []

    event_items = []
    for e in events.find({"owner_id": user_id}):
        if query in (e.get("title", "")).lower() or query in (e.get("subject", "")).lower() or query in (e.get("location", "")).lower():
            event_items.append({
                "id": str(e["_id"]),
                "title": e["title"],
                "subtitle": f"{e['date']} at {e['time']}" + (f" — {e['location']}" if e.get("location") else ""),
                "type": "event",
                "color": "#5C6BC0",
            })
    if event_items:
        results.append({"category": "Classes", "items": event_items})

    task_items = []
    for t in tasks.find({"owner_id": user_id}):
        if query in (t.get("title", "")).lower() or query in (t.get("category", "")).lower() or query in (t.get("notes", "")).lower():
            task_items.append({
                "id": str(t["_id"]),
                "title": t["title"],
                "subtitle": f"{t.get('due_date', '')} {t.get('due_time', '')}" + (f" — {t['category']}" if t.get("category") else "") + (" ✓" if t.get("completed") else ""),
                "type": "task",
                "color": "#FFA726",
            })
    if task_items:
        results.append({"category": "Tasks", "items": task_items})

    assignment_items = []
    for a in assignments.find({"owner_id": user_id}):
        if query in (a.get("title", "")).lower() or query in (a.get("subject", "")).lower() or query in (a.get("notes", "")).lower() or query in (a.get("attachment", "")).lower():
            assignment_items.append({
                "id": str(a["_id"]),
                "title": a["title"],
                "subtitle": f"{a.get('due_date', '')} {a.get('due_time', '')}" + (f" — {a['subject']}" if a.get("subject") else "") + (" ✓" if a.get("completed") else ""),
                "type": "assignment",
                "color": "#FF7043",
            })
    if assignment_items:
        results.append({"category": "Assignments", "items": assignment_items})

    exam_items = []
    for e in exams.find({"owner_id": user_id}):
        if query in (e.get("title", "")).lower() or query in (e.get("subject", "")).lower() or query in (e.get("location", "")).lower() or query in (e.get("exam_type", "")).lower():
            exam_items.append({
                "id": str(e["_id"]),
                "title": e["title"],
                "subtitle": f"{e['date']} at {e['time']}" + (f" — {e['exam_type']}" if e.get("exam_type") else "") + (f" in {e['location']}" if e.get("location") else ""),
                "type": "exam",
                "color": "#EF5350",
            })
    if exam_items:
        results.append({"category": "Exams", "items": exam_items})

    note_items = []
    for n in notes.find({"owner_id": user_id}):
        if query in (n.get("title", "")).lower() or query in (n.get("content", "")).lower() or query in (n.get("subject", "")).lower():
            content_preview = n.get("content", "")[:60]
            if len(n.get("content", "")) > 60:
                content_preview += "..."
            note_items.append({
                "id": str(n["_id"]),
                "title": n["title"],
                "subtitle": content_preview + (f" — {n['subject']}" if n.get("subject") else ""),
                "type": "note",
                "color": "#26A69A",
            })
    if note_items:
        results.append({"category": "Notes", "items": note_items})

    tt_items = []
    for t in timetable.find({"owner_id": user_id}):
        if query in (t.get("title", "")).lower() or query in (t.get("subject", "")).lower() or query in (t.get("location", "")).lower():
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            day = day_names[t.get("day_of_week", 0)]
            tt_items.append({
                "id": str(t["_id"]),
                "title": t["title"],
                "subtitle": f"{day} at {t['time']}" + (f" — {t['location']}" if t.get("location") else ""),
                "type": "timetable",
                "color": "#42A5F5",
            })
    if tt_items:
        results.append({"category": "Timetable", "items": tt_items})

    return results
